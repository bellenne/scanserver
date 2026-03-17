from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from modes.base import ModeBase
from modes.compare_fill import _extract_key_from_payload

log = logging.getLogger("mode.compare")


@dataclass
class PendingCompare3:
    first_payload: str
    first_key: str
    second_payload: str | None = None
    second_key: str | None = None
    ts: float = 0.0


class CompareMode(ModeBase):
    def __init__(self, timeout_s: float = 45.0) -> None:
        super().__init__(name="COMPARE")
        self._pending: dict[str, PendingCompare3] = {}
        self.timeout_s = float(timeout_s)

    def on_scan(self, session: "ScannerSession", payload: str) -> None:
        now = time.time()
        dev = session.device_id

        pending = self._pending.get(dev)
        if pending and (now - pending.ts) > self.timeout_s:
            log.info("[%s] COMPARE pending expired (%.1fs)", dev, now - pending.ts)
            self._pending.pop(dev, None)
            pending = None

        current_key = _extract_key_from_payload(payload)

        if pending is None:
            self._pending[dev] = PendingCompare3(
                first_payload=payload,
                first_key=current_key,
                ts=now,
            )
            session.tts.say("Первый принят. Жду второй.")
            log.info("[%s] COMPARE step1 key=%s payload=%s", dev, current_key, payload)
            return

        if pending.second_payload is None:
            if pending.first_key != current_key:
                self._pending.pop(dev, None)
                session.tts.say("Не верно.")
                log.info(
                    "[%s] COMPARE step2 fail: first_key=%s second_key=%s first_payload=%s second_payload=%s",
                    dev,
                    pending.first_key,
                    current_key,
                    pending.first_payload,
                    payload,
                )
                return

            pending.second_payload = payload
            pending.second_key = current_key
            pending.ts = now
            session.tts.say("Второй принят. Жду третий.")
            log.info("[%s] COMPARE step2 ok: key=%s payload=%s", dev, current_key, payload)
            return

        self._pending.pop(dev, None)

        if pending.first_key == current_key:
            session.tts.say("Всё верно.")
            log.info(
                "[%s] COMPARE success: key=%s first_payload=%s second_payload=%s third_payload=%s",
                dev,
                current_key,
                pending.first_payload,
                pending.second_payload,
                payload,
            )
            return

        session.tts.say("Не верно.")
        log.info(
            "[%s] COMPARE step3 fail: first_key=%s third_key=%s first_payload=%s second_payload=%s third_payload=%s",
            dev,
            pending.first_key,
            current_key,
            pending.first_payload,
            pending.second_payload,
            payload,
        )
