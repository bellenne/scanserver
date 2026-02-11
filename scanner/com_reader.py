from __future__ import annotations

import logging
import time
from typing import Callable, Optional

import serial  # type: ignore

log = logging.getLogger("scanner.com")


class ComReader:
    def __init__(
        self,
        port: str,
        baudrate: int,
        on_line: Callable[[str], None],
        reconnect_delay_s: float = 1.5,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.on_line = on_line
        self.reconnect_delay_s = reconnect_delay_s
        self._stop = False
        self._ser: Optional[serial.Serial] = None

    def stop(self) -> None:
        self._stop = True
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
        except Exception:
            pass

    def run_forever(self) -> None:
        while not self._stop:
            try:
                self._connect()
                self._read_loop()
            except Exception as e:
                log.warning("COM error on %s: %s", self.port, e)
            finally:
                try:
                    if self._ser and self._ser.is_open:
                        self._ser.close()
                except Exception:
                    pass
                self._ser = None

            if not self._stop:
                time.sleep(self.reconnect_delay_s)

    def _connect(self) -> None:
        log.info("Connecting %s @ %s", self.port, self.baudrate)
        self._ser = serial.Serial(self.port, self.baudrate, timeout=1)

    def _read_loop(self) -> None:
        assert self._ser is not None
        while not self._stop:
            raw = self._ser.readline()  # до \n
            if not raw:
                continue
            try:
                line = raw.decode(errors="ignore").strip()
            except Exception:
                continue
            if line:
                self.on_line(line)
