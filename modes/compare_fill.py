from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from modes.base import ModeBase

log = logging.getLogger("mode.compare_fill")


@dataclass
class PendingCompare:
    key: str
    payload: str
    ts: float


def _normalize_key(s: str) -> str:
    """Нормализация ключа для устойчивого сравнения:
       - strip, lower
       - заменить кириллическую 'х' на латинскую 'x'
       - убрать лишние пробелы
    """
    if s is None:
        return ""
    s = str(s).strip()
    # replace cyrillic small/large 'х' (U+0445/U+0425) to latin x
    s = s.replace("\u0445", "x").replace("\u0425", "x")
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

    # безопасно работать со строкой
    p = str(payload)

    # split by '|' into parts
    parts = p.split("|")

    # ищем art=... в любых частях
    for part in parts:
        # нормализуем разделители и пробелы внутри части
        part_stripped = part.strip()
        if "=" in part_stripped:
            k, _, v = part_stripped.partition("=")
            if k.strip().lower() == "art":
                return _normalize_key(v)

    # если art не найден — возьмём первую часть до |
    if len(parts) >= 1 and parts[0].strip() != "":
        return _normalize_key(parts[0].strip())

    # fallback — весь payload
    return _normalize_key(p)


class CompareFillMode(ModeBase):
    """
    Двухшаговое сравнение:
      - Первый скан: сохраняем ключ (pending) и говорим "Первый принят. Жду второй."
      - Второй скан: извлекаем ключ, сравниваем с pending.key (независимо от порядка сканирования)
         - если совпало: говорим "Всё верно.", отправляем post_event(action="done", payload=<текущий_payload>)
         - если не совпало: говорим "Не верно."
      - pending очищается после сравнения или по таймауту
    """

    def __init__(self, timeout_s: float = 30.0) -> None:
        super().__init__(name="COMPARE_FILL")
        # pending per device_id
        self._pending: dict[str, PendingCompare] = {}
        self.timeout_s = float(timeout_s)

    def on_scan(self, session: "ScannerSession", payload: str) -> None:
        now = time.time()
        dev = session.device_id

        # очистка просроченного pending
        pend = self._pending.get(dev)
        if pend and (now - pend.ts) > self.timeout_s:
            log.info("[%s] pending expired (%.1fs)", dev, now - pend.ts)
            self._pending.pop(dev, None)
            pend = None

        # извлекаем ключ текущего payload
        cur_key = _extract_key_from_payload(payload)

        # если нет pending — ставим текущий как pending
        if pend is None:
            self._pending[dev] = PendingCompare(key=cur_key, payload=payload, ts=now)
            session.tts.say("Первый принят. Жду второй.")
            log.info("[%s] COMPARE pending set key=%s payload=%s", dev, cur_key, payload)
            return

        # есть pending — сравниваем
        first_key = pend.key
        first_payload = pend.payload

        # очищаем pending сразу (чтобы не было повторов)
        self._pending.pop(dev, None)

        # Рассмотрим два варианта: pending.key == cur_key
        ok = False
        try:
            ok = (first_key == cur_key)
        except Exception:
            ok = False

        if ok:
            session.tts.say("Всё верно.")
            log.info("[%s] COMPARE OK: key=%s (first_payload=%s, second_payload=%s)", dev, cur_key, first_payload, payload)

            # отправляем событие. В качестве payload отправим второй скан (как было договорено)
            try:
                session.post_event(action="done", payload=payload)
            except Exception as e:
                log.warning("[%s] COMPARE post failed: %s", dev, e)
                session.tts.say("Ошибка отправки")
        else:
            # Попробуем добавить чуть более гибкое сравнение: если один ключ может содержать источник/суффикс,
            # можно попытаться сравнить по подстроке. (опционально)
            # По умолчанию — строгая проверка, но можно сделать tolerant:
            fk = first_key or ""
            ck = cur_key or ""
            tolerant = False
            try:
                # если одна строка является подстрокой другой -> допускаем как совпадение
                if fk and ck and (fk in ck or ck in fk):
                    tolerant = True
            except Exception:
                tolerant = False

            if tolerant:
                session.tts.say("Всё верно.")
                log.info("[%s] COMPARE OK (tolerant): first=%s second=%s", dev, fk, ck)
                try:
                    session.post_event(action="done", payload=payload)
                except Exception as e:
                    log.warning("[%s] COMPARE post failed (tolerant): %s", dev, e)
                    session.tts.say("Ошибка отправки")
                return

            session.tts.say("Не верно.")
            log.info("[%s] COMPARE FAIL: first_key=%s second_key=%s (first_payload=%s, second_payload=%s)", dev, first_key, cur_key, first_payload, payload)
