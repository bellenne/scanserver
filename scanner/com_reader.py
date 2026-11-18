from __future__ import annotations

import logging
import re
import time
from typing import Callable, Optional

import serial  # type: ignore

log = logging.getLogger("scanner.com")

# Scanners terminate a code with CR, LF or CRLF depending on their suffix setting.
_LINE_END = re.compile(rb"[\r\n]")
# Serial read timeout: how often the loop wakes up when the port is silent.
_READ_TIMEOUT_S = 0.1
# A code without any terminator is emitted after this much silence.
_IDLE_FLUSH_S = 0.3


class ComReader:
    def __init__(
        self,
        port: str,
        baudrate: int,
        on_line: Callable[[str], None],
        on_connected: Callable[[], None] | None = None,
        reconnect_delay_s: float = 1.5,
        encoding: str = "utf-8",
        on_decode_error: Callable[[], None] | None = None,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.on_line = on_line
        self.on_connected = on_connected
        self.reconnect_delay_s = reconnect_delay_s
        self.encoding = encoding
        self.on_decode_error = on_decode_error
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
        self._ser = serial.Serial(self.port, self.baudrate, timeout=_READ_TIMEOUT_S)
        if self.on_connected is not None:
            self.on_connected()

    def _read_loop(self) -> None:
        # readline() only splits on LF: with a CR-only scanner suffix every code
        # was delayed by the read timeout and quick repeat scans merged into one
        # payload ("QR\rQR"), which MES rejected. Split on CR/LF ourselves.
        assert self._ser is not None
        buf = bytearray()
        last_rx = time.monotonic()
        while not self._stop:
            chunk = self._ser.read(self._ser.in_waiting or 1)
            now = time.monotonic()
            if chunk:
                buf += chunk
                last_rx = now
                *lines, rest = _LINE_END.split(bytes(buf))
                buf = bytearray(rest)
                for raw in lines:
                    self._emit(raw)
            elif buf and now - last_rx >= _IDLE_FLUSH_S:
                self._emit(bytes(buf))
                buf.clear()

    def _emit(self, raw: bytes) -> None:
        if not raw.strip():
            return
        try:
            line = raw.decode(self.encoding).strip()
        except UnicodeDecodeError:
            log.error("QR decoding failed on %s with encoding %s; raw_hex=%s",
                      self.port, self.encoding, raw[:200].hex())
            if self.on_decode_error is not None:
                self.on_decode_error()
            return
        if line:
            self.on_line(line)
