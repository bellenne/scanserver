from __future__ import annotations

import logging
import httpx

from modes.base import ModeBase

log = logging.getLogger("mode.package")


class PackageMode(ModeBase):
    def __init__(self) -> None:
        super().__init__(name="PACKAGE")

    def on_scan(self, session: "ScannerSession", payload: str) -> None:
        # user gate (обычно уже в router, но подстрахуемся)
        if session.get_user_id() is None:
            session.tts.say("Сначала выберите пользователя")
            return

        try:
            # отправляем "в том же формате"
            # action: для упаковки логично "done" (если на сервере action in: done,defect)
            session.post_event(
                action="done",
                payload=payload,
                endpoint=session.endpoints.package,
            )
            session.tts.say("Упаковано")
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError):
            session.tts.say("Нет соединения с сервером")
        except httpx.HTTPStatusError as e:
            log.warning("[%s] PACKAGE post failed: %s", session.device_id, e)
            session.tts.say("Ошибка отправки")
        except Exception as e:
            log.warning("[%s] PACKAGE unexpected error: %s", session.device_id, e)
            session.tts.say("Ошибка отправки")