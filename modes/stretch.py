from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from modes.base import ModeBase

if TYPE_CHECKING:
    from scanner.session import ScannerSession

log = logging.getLogger("mode.stretch")


class StretchMode(ModeBase):
    def __init__(self) -> None:
        super().__init__(name="STRETCH")

    def on_scan(self, session: "ScannerSession", payload: str) -> None:
        if session.get_user_id() is None:
            session.tts.say("Сначала выберите пользователя")
            return

        # Второй этап выполняется только после успешного ответа на резку.
        for stage, endpoint, error_message in (
            ("cut", session.endpoints.events, "Ошибка отправки резки"),
            ("stretch", session.endpoints.stretch, "Резка отправлена. Ошибка отправки натяжки"),
        ):
            try:
                session.post_event(action="done", payload=payload, endpoint=endpoint)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                log.warning("[%s] STRETCH %s network error: %s", session.device_id, stage, e)
                session.tts.say(f"{error_message}. Нет соединения с сервером")
                return
            except Exception as e:
                log.warning("[%s] STRETCH %s post failed: %s", session.device_id, stage, e)
                session.tts.say(error_message)
                return

        session.tts.say("Натяжка выполнена")
