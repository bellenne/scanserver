from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from api.client import ApiClient
from api.users_cache import UsersCache
from core.state_store import StateStore
from core.time_utils import iso_now_local
from scanner.com_reader import ComReader
from scanner.router import Router
from scanner.svc_commands import ModeName
from tts.manager import TTSManager
from modes.compare_fill import CompareFillMode
from modes.defect import DefectMode
from modes.transfer import TransferMode
from modes.transfer_defect import TransferDefectMode
from modes.base import Mode
from core.config import Endpoints
import httpx
import time

log = logging.getLogger("scanner.session")

class SessionSpeaker:
    def __init__(self, base_tts, session: "ScannerSession") -> None:
        self._tts = base_tts
        self._session = session

    def say(self, text: str) -> None:
        t = (text or "").strip()
        if not t:
            return

        # метка сканера (коротко)
        dev = self._session.device_id
        dev_short = dev.split("-")[-1] if dev else dev  # например "01"

        self._tts.say(f"{dev}. {t}")

@dataclass
class ScannerSessionState:
    user_id: int | None
    user_name: str | None
    mode: ModeName


class ScannerSession:
    def __init__(
        self,
        device_id: str,
        com_port: str,
        baudrate: int,
        api: ApiClient,
        users_cache: UsersCache,
        tts: TTSManager,
        state_store: StateStore,
        global_state: dict,
        endpoints: Endpoints,
    ) -> None:
        self.device_id = device_id
        self.com_port = com_port
        self.baudrate = baudrate

        self.api = api
        self.users_cache = users_cache
        self.tts = SessionSpeaker(tts, self)

        self.state_store = state_store
        self.global_state = global_state
        self.endpoints = endpoints

        self._router = Router()
        self._stop = threading.Event()

        self._state = self._load_state()

        self._modes: dict[ModeName, Mode] = {
            "COMPARE_FILL": CompareFillMode(),
            "DEFECT": DefectMode(),
            "TRANSFER": TransferMode(),
            "TRANSFER_DEFECT": TransferDefectMode(),
        }

        self._reader = ComReader(
            port=self.com_port,
            baudrate=self.baudrate,
            on_line=self.on_line,
        )

        self._thread = threading.Thread(target=self._reader.run_forever, name=f"com-{device_id}", daemon=True)

        self._last_activity_ts: float | None = None
        self._idle_timeout_s = 1 * 60
        self._idle_thread: threading.Thread | None = None

    def touch_activity(self) -> None:
        if self._state.user_id is None:
            return
        self._last_activity_ts = time.time()

    def _idle_watchdog(self) -> None:
        while not self._stop.is_set():
            try:
                if self._state.user_id is not None and self._last_activity_ts is not None:
                    if (time.time() - self._last_activity_ts) >= self._idle_timeout_s:
                        # сбрасываем пользователя
                        self._state.user_id = None
                        self._state.user_name = None
                        self._persist_state()
                        self.tts.say("Пользователь снят по таймауту")
                        log.info("[%s] user auto-cleared by idle timeout", self.device_id)

                        self._last_activity_ts = None
            except Exception as e:
                log.warning("[%s] idle watchdog error: %s", self.device_id, e)

            self._stop.wait(5.0)  # проверка каждые 5 секунд

    def start(self) -> None:
        log.info("[%s] start session on %s", self.device_id, self.com_port)
        self._thread.start()
        if self._state.user_id is None:
            self.tts.say(f"Сканер {self.device_id} запущен. Ожидаю пользователя.")
        else:
            if self._state.user_name:
                self.tts.say(f"Сканер {self.device_id} запущен. Пользователь: {self._state.user_name}.")
            else:
                self.tts.say(f"Сканер {self.device_id} запущен. Пользователь {self._state.user_id}.")
        self._idle_thread = threading.Thread(target=self._idle_watchdog, daemon=True, name=f"idle-{self.device_id}")
        self._idle_thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._reader.stop()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout=timeout)

    def on_line(self, line: str) -> None:
        log.info("[%s] <- %s", self.device_id, line)
        self._router.route(self, line)

    def get_user_name(self) -> str | None:
        return self._state.user_name

    def set_user(self, user_id: int, reason: str = "manual") -> None:
        cur = self._state.user_id
        if cur is not None and int(cur) == int(user_id):
            self.clear_user(reason="toggle")
            return
        # 1) Пытаемся сходить на сервер: /api/v1/users/{id}
        try:
            data = self.api.get_user(int(user_id))
        except httpx.HTTPStatusError as e:
            # сервер ответил, но статус не 2xx
            status = e.response.status_code
            log.warning("[%s] set_user http error %s", self.device_id, status)

            # 400/404/422 — трактуем как неверный id
            if status in (400, 404, 422):
                self.tts.say("Неверный id пользователя")
            else:
                self.tts.say("Нет соединения с сервером")
            return
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
            log.warning("[%s] set_user network error: %s", self.device_id, e)
            self.tts.say("Нет соединения с сервером")
            return
        except Exception as e:
            # на всякий
            log.warning("[%s] set_user unexpected error: %s", self.device_id, e)
            self.tts.say("Нет соединения с сервером")
            return

        # 2) Валидация ответа
        try:
            rid = int(data.get("id"))
            name = str(data.get("name", "")).strip()
        except Exception:
            rid = -1
            name = ""

        if rid != int(user_id) or not name:
            # сервер ответил чем-то не тем или id нет/не совпал
            self.tts.say("Неверный id пользователя")
            return

        # 3) Всё ок — сохраняем и пускаем
        self._state.user_id = int(user_id)
        self._state.user_name = name
        self._persist_state()

        self.tts.say(f"Пользователь: {name}")
        log.info("[%s] user set to %s (%s)", self.device_id, user_id, reason)
        self._last_activity_ts = time.time()

    def set_mode(self, mode: ModeName, reason: str = "manual") -> None:
        self._state.mode = mode
        self._persist_state()
        modes = {"COMPARE_FILL":"рЕзка", "DEFECT":"Брак рЕзки", "TRANSFER":"Перенос", "TRANSFER_DEFECT":"Брак переноса"}
        self.tts.say(f"Режим {modes[mode]}")
        log.info("[%s] mode set to %s (%s)", self.device_id, mode, reason)

    def get_mode_handler(self) -> Mode:
        return self._modes[self._state.mode]

    def get_user_id(self) -> int | None:
        return self._state.user_id

    def post_event(self, action: str, payload: str, extra: dict | None = None, endpoint: str | None = None) -> None:
        if self._state.user_id is None:
            raise RuntimeError("User is not set for this scanner")
        body = {
            "payload": payload,
            "action": action,
            "user_id": self._state.user_id,
            "device_id": self.device_id,  # строго сканер
            "client_ts": iso_now_local(),
        }
        if extra:
            body.update(extra)

        path = endpoint or self.endpoints.events
        self.api.post_json(path, body)

    def _load_state(self) -> ScannerSessionState:
        devices = self.global_state.get("devices", {})
        d = devices.get(self.device_id, {}) if isinstance(devices, dict) else {}

        user_id = None
        user_name = None
        mode = d.get("mode", "COMPARE_FILL")

        if mode not in ("COMPARE_FILL", "DEFECT", "TRANSFER","TRANSFER_DEFECT"):
            mode = "COMPARE_FILL"

        try:
            user_id = int(user_id) if user_id is not None else None
        except Exception:
            user_id = None

        user_name = str(user_name) if user_name is not None else None

        return ScannerSessionState(user_id=user_id, user_name=user_name, mode=mode)  # type: ignore[arg-type]

    def _persist_state(self) -> None:
        devices = self.global_state.setdefault("devices", {})
        devices[self.device_id] = {
            "user_id": self._state.user_id,
            "user_name": self._state.user_name,
            "mode": self._state.mode,
            "com_port": self.com_port,
        }
        self.state_store.save(self.global_state)
    
    def clear_user(self, reason: str = "manual") -> None:
        self._state.user_id = None
        self._state.user_name = None
        self._persist_state()
        self.tts.say("Пользователь снят")
        log.info("[%s] user cleared (%s)", self.device_id, reason)

    