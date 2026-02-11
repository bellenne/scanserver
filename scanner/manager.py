from __future__ import annotations

import logging
import threading

from api.client import ApiClient
from api.users_cache import UsersCache
from core.state_store import StateStore
from core.config import ScannerConfig, Endpoints
from scanner.session import ScannerSession
from tts.manager import TTSManager

log = logging.getLogger("scanner.manager")


class ScannerManager:
    def __init__(
        self,
        api: ApiClient,
        users_cache: UsersCache,
        tts: TTSManager,
        state: StateStore,
        initial_state: dict,
        scanners: list[ScannerConfig],
        endpoints: Endpoints,
    ) -> None:
        self.api = api
        self.users_cache = users_cache
        self.tts = tts
        self.state = state
        self.state_data = initial_state
        self.scanners_cfg = scanners
        self.endpoints = endpoints

        self._sessions: list[ScannerSession] = []
        self._stop = threading.Event()

    def start(self) -> None:
        if not self.scanners_cfg:
            log.warning("No scanners configured. Add scanners[] to config.json.")
            return

        for s in self.scanners_cfg:
            sess = ScannerSession(
                device_id=s.device_id,
                com_port=s.com_port,
                baudrate=s.baudrate,
                api=self.api,
                users_cache=self.users_cache,
                tts=self.tts,
                state_store=self.state,
                global_state=self.state_data,
                endpoints=self.endpoints,
            )
            self._sessions.append(sess)
            sess.start()

    def stop(self) -> None:
        for s in self._sessions:
            s.stop()

        try:
            self.api.close()
        except Exception:
            pass

        self._stop.set()

    def wait(self) -> None:
        try:
            while not self._stop.is_set():
                for s in self._sessions:
                    if s._thread.is_alive():
                        break
                else:
                    # все сессии завершены
                    break
                self._stop.wait(0.5)
        except KeyboardInterrupt:
            self.stop()
