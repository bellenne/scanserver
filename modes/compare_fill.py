from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from modes.base import ModeBase

log = logging.getLogger("mode.compare_fill")


@dataclass
class PendingCompare:
    key: str
    data_payload: str | None = None
    payloads: list[str] = field(default_factory=list)
    ts: float = 0.0


def _normalize_key(s: str) -> str:
    """Нормализация ключа для устойчивого сравнения:
       - strip, lower
       - заменить кириллическую 'х' на латинскую 'x'
       - убрать лишние пробелы
    """
    if s is None:
        return ""
    s = str(s).strip()
    s = s.replace("х", "x").replace("Х", "x")
    s = s.replace(" ", "")
    return s.lower()


def _extract_key_from_payload(payload: str) -> str:
    """
    Попытаться вытащить "ключ сравнения" из payload.
    Правила:
      - Если внутри payload есть сегменты через '|' и среди них есть 'art=VALUE' -> вернуть VALUE
      - Иначе если payload содержит '|' -> вернуть часть до первого '|'
      - Иначе вернуть весь payload
    """
    if not payload:
        return ""

    p = str(payload)
    parts = p.split("|")

    for part in parts:
        part_stripped = part.strip()
        if "=" in part_stripped:
            k, _, v = part_stripped.partition("=")
            if k.strip().lower() == "art":
                return _normalize_key(v)

    if len(parts) >= 1 and parts[0].strip() != "":
        return _normalize_key(parts[0].strip())

    return _normalize_key(p)


def _keys_match(expected_key: str, current_key: str) -> bool:
    try:
        if expected_key == current_key:
            return True
    except Exception:
        return False

    ek = expected_key or ""
    ck = current_key or ""
    try:
        return bool(ek and ck and (ek in ck or ck in ek))
    except Exception:
        return False


def _is_data_payload(payload: str) -> bool:
    p = str(payload or "")
    parts = [part.strip() for part in p.split("|") if part.strip()]
    if len(parts) < 2:
        return False

    has_art = False
    has_meta = False
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        key = key.strip().lower()
        value = value.strip()
        if not value:
            continue
        if key == "art":
            has_art = True
        else:
            has_meta = True

    return has_art and has_meta


class CompareFillMode(ModeBase):
    """
    Трёхшаговое сравнение в любом порядке сканирования:
      - нужно собрать 3 QR с одним и тем же артикулом
      - среди них должен быть один полный QR с данными
      - на сервер отправляем именно этот полный QR
    """

    def __init__(self, timeout_s: float = 45.0) -> None:
        super().__init__(name="COMPARE_FILL")
        self._pending: dict[str, PendingCompare] = {}
        self.timeout_s = float(timeout_s)

    def on_scan(self, session: "ScannerSession", payload: str) -> None:
        now = time.time()
        dev = session.device_id

        pending = self._pending.get(dev)
        if pending and (now - pending.ts) > self.timeout_s:
            log.info("[%s] COMPARE_FILL pending expired (%.1fs)", dev, now - pending.ts)
            self._pending.pop(dev, None)
            pending = None

        current_key = _extract_key_from_payload(payload)
        current_is_data = _is_data_payload(payload)

        if pending is None:
            self._pending[dev] = PendingCompare(
                key=current_key,
                data_payload=payload if current_is_data else None,
                payloads=[payload],
                ts=now,
            )
            session.tts.say("Первый принят. Жду второй.")
            log.info("[%s] COMPARE_FILL step1 key=%s payload=%s data=%s", dev, current_key, payload, current_is_data)
            return

        if not _keys_match(pending.key, current_key):
            self._pending.pop(dev, None)
            session.tts.say("Не верно.")
            log.info(
                "[%s] COMPARE_FILL fail: expected_key=%s current_key=%s payloads=%s current_payload=%s",
                dev,
                pending.key,
                current_key,
                pending.payloads,
                payload,
            )
            return

        pending.payloads.append(payload)
        pending.ts = now
        if current_is_data and pending.data_payload is None:
            pending.data_payload = payload

        scans_count = len(pending.payloads)
        if scans_count == 2:
            session.tts.say("Второй принят. Жду третий.")
            log.info("[%s] COMPARE_FILL step2 ok: key=%s payload=%s data=%s", dev, current_key, payload, current_is_data)
            return

        self._pending.pop(dev, None)

        if pending.data_payload is None:
            session.tts.say("Не найден QR с данными.")
            log.info(
                "[%s] COMPARE_FILL fail: no data QR found for key=%s payloads=%s",
                dev,
                pending.key,
                pending.payloads,
            )
            return

        session.tts.say("Всё верно.")
        log.info(
            "[%s] COMPARE_FILL success: key=%s payloads=%s data_payload=%s",
            dev,
            pending.key,
            pending.payloads,
            pending.data_payload,
        )
        try:
            session.post_event(action="done", payload=pending.data_payload)
        except Exception as e:
            log.warning("[%s] COMPARE_FILL post failed: %s", dev, e)
            session.tts.say("Ошибка отправки")
