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

        # MES closes both stages atomically through this endpoint.
        try:
            result = session.post_event(action="done", payload=payload, endpoint=session.endpoints.stretch)
        except httpx.TransportError as e:
            # Timeout / dropped connection / server closed without response:
            # MES may have committed, the repeat scan is recognised as duplicate.
            log.warning("[%s] STRETCH network error: %s", session.device_id, e)
            session.tts.say("Нет подтверждения натяжки. Проверьте соединение и повторите сканирование")
            return
        except Exception as e:
            log.warning("[%s] STRETCH post failed: %s", session.device_id, e)
            session.tts.say("Ошибка отправки натяжки. Проверьте журнал")
            return

        if not isinstance(result, dict) or result.get("ok") is not True:
            log.warning("[%s] STRETCH MES did not confirm success: %r", session.device_id, result)
            session.tts.say("Сервер не подтвердил натяжку. Проверьте журнал")
            return

        stages = result.get("stages")
        for stage in ("cut", "stretch"):
            operation = stages.get(stage) if isinstance(stages, dict) else None
            if not isinstance(operation, dict) or operation.get("status") != "done":
                log.warning("[%s] STRETCH incomplete MES result: %r", session.device_id, result)
                session.tts.say("Сервер не подтвердил завершение резки и натяжки. Проверьте MES")
                return
            if not operation.get("report_id"):
                log.warning("[%s] STRETCH missing %s report: %r", session.device_id, stage, result)
                session.tts.say("Этап отмечен готовым, но отчёт отсутствует. Проверьте MES")
                return

        if result.get("duplicate") is True:
            session.tts.say("Резка и натяжка уже выполнены")
            return

        session.tts.say("Натяжка выполнена")
