from __future__ import annotations

import logging
import threading

import httpx

from modes.base import ModeBase
from ui.transfer_window import show_transfer_window

log = logging.getLogger("mode.transfer")


class TransferMode(ModeBase):
    def __init__(self) -> None:
        super().__init__(name="TRANSFER")

    def on_scan(self, session: "ScannerSession", payload: str) -> None:
        # user gate обычно уже в router, но подстрахуемся
        if session.get_user_id() is None:
            session.tts.say("Сначала выберите пользователя")
            return

        session.tts.say("QR принят. Заполните перенос.")
        t = threading.Thread(
            target=self._flow,
            args=(session, payload),
            name=f"transfer-ui-{session.device_id}",
            daemon=True,
        )
        t.start()

    def _flow(self, session: "ScannerSession", payload: str) -> None:
        try:
            user_id = session.get_user_id()
            if user_id is None:
                session.tts.say("Сначала выберите пользователя")
                return

            user_name = session.get_user_name() or str(user_id)

            result = show_transfer_window(
                title="Отчётность переноса",
                payload=payload,
                user_name=user_name,
                device_id=session.device_id,
                with_comment=False,
            )

            if result is None:
                session.tts.say("Отменено")
                return

            done_map = result.get("done_map")
            if not isinstance(done_map, dict) or not done_map:
                session.tts.say("Заполните размеры")
                return

            # Отправка на тот же роут (events), action строго done/defect -> тут done
            # done_map должен уйти как array/object — Laravel примет как массив
            session.post_event(
                action="done",
                payload=payload,
                extra={"done_map": done_map},
                endpoint=session.endpoints.transfer,
            )

            session.tts.say("Отправлено")

        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError):
            session.tts.say("Нет соединения с сервером")
        except httpx.HTTPStatusError:
            session.tts.say("Ошибка отправки")
        except Exception as e:
            log.warning("Transfer flow failed: %s", e)
            session.tts.say("Ошибка отправки")
