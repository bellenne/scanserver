from __future__ import annotations

import logging
import threading

from modes.base import ModeBase
from ui.defect_window import show_defect_window

log = logging.getLogger("mode.defect")


class DefectMode(ModeBase):
    def __init__(self) -> None:
        super().__init__(name="DEFECT")

    def on_scan(self, session: "ScannerSession", payload: str) -> None:
        # user gate уже есть в router, но на всякий
        if session.get_user_id() is None:
            session.tts.say("Сначала выберите пользователя")
            return

        session.tts.say("QR принят. Заполните дефект.")
        t = threading.Thread(
            target=self._flow,
            args=(session, payload),
            name=f"defect-ui-{session.device_id}",
            daemon=True,
        )
        t.start()

    def _flow(self, session: "ScannerSession", payload: str) -> None:
        """
        DEFECT flow:
        - открываем UI
        - если Cancel -> голос "Отменено"
        - если Send -> формируем body под Laravel валидацию:
            payload, action(defect), user_id, (panels[] | qty), reason, device_id, client_ts
            и отправляем на endpoint дефекта
        """
        import httpx

        try:
            user_id = session.get_user_id()
            if user_id is None:
                session.tts.say("Сначала выберите пользователя")
                return

            user_name = session.get_user_name() or str(user_id)

            # UI: возвращает dict либо None
            result = show_defect_window(
                payload=payload,
                user_name=user_name,
                device_id=session.device_id,
            )

            if result is None:
                session.tts.say("Отменено")
                return

            product_type = (result.get("product_type") or "").strip()  # "tshirt" | "wallpaper"
            raw_numbers = (result.get("numbers") or "").strip()        # qty или "1,2,3"
            comment = (result.get("comment") or "").strip()

            if not raw_numbers:
                session.tts.say("Заполните поле")
                return

            extra: dict = {}
            if comment:
                extra["reason"] = comment

            # Преобразуем под правила сервера
            if product_type == "tshirt":
                # qty: int>=1
                try:
                    qty = int(raw_numbers)
                    if qty < 1:
                        raise ValueError
                except Exception:
                    session.tts.say("Неверное количество")
                    return

                extra["qty"] = qty
                # done_map опционально, пока не шлём

            elif product_type == "wallpaper":
                panels = _parse_panels(raw_numbers)  # list[int] 1..99
                if not panels:
                    session.tts.say("Неверные номера полотен")
                    return
                extra["panels"] = panels

            else:
                session.tts.say("Выберите тип изделия")
                return

            # Отправка (action строго done/defect -> тут defect)
            session.post_event(
                action="defect",
                payload=payload,
                extra=extra,
                endpoint=session.endpoints.defect,
            )

            session.tts.say("Отправлено")

        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError):
            session.tts.say("Нет соединения с сервером")
        except httpx.HTTPStatusError:
            # сервер ответил, но статус не 2xx (валидация и т.п.)
            session.tts.say("Ошибка отправки")
        except Exception as e:
            log.warning("Defect flow failed: %s", e)
            session.tts.say("Ошибка отправки")
    
def _parse_panels(s: str) -> list[int]:
    # "1,2,3" -> [1,2,3], строго int 1..99, без мусора
    cleaned = s.replace(" ", "")
    if not cleaned:
        return []

    parts = cleaned.split(",")
    out: list[int] = []
    for p in parts:
        if not p:
            continue
        try:
            v = int(p)
        except Exception:
            return []
        if v < 1 or v > 99:
            return []
        out.append(v)

    # убрать дубликаты, сохранив порядок
    seen = set()
    uniq: list[int] = []
    for v in out:
        if v in seen:
            continue
        seen.add(v)
        uniq.append(v)
    return uniq