from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, call

import serial  # type: ignore

from core.config import load_config
from scanner.com_reader import ComReader


class ComReaderTests(unittest.TestCase):
    def read_chunks(self, chunks: list[bytes], encoding: str = "utf-8", gap_s: float = 0.0,
                    settle_s: float = 0.6) -> tuple[Mock, Mock]:
        """Feed bytes through a pyserial loopback port into the real read loop."""
        on_line, on_error = Mock(), Mock()
        reader = ComReader("TEST", 9600, on_line, encoding=encoding, on_decode_error=on_error)
        reader._ser = serial.serial_for_url("loop://", timeout=0.1)
        thread = threading.Thread(target=reader._read_loop, daemon=True)
        thread.start()
        for chunk in chunks:
            reader._ser.write(chunk)
            if gap_s:
                time.sleep(gap_s)
        time.sleep(settle_s)
        reader._stop = True
        thread.join(timeout=2.0)
        self.assertFalse(thread.is_alive(), "COM read loop did not stop")
        return on_line, on_error

    def read_once(self, raw: bytes, encoding: str = "utf-8") -> tuple[Mock, Mock]:
        return self.read_chunks([raw], encoding)

    def test_any_line_terminator_ends_a_code(self) -> None:
        for term in (b"\r\n", b"\n", b"\r"):
            with self.subTest(term=term):
                line, error = self.read_chunks([b"QR-ONE" + term + b"QR-TWO" + term], settle_s=0.2)
                self.assertEqual(line.call_args_list, [call("QR-ONE"), call("QR-TWO")])
                error.assert_not_called()

    def test_quick_repeat_scans_with_cr_suffix_are_not_merged(self) -> None:
        line, _ = self.read_chunks([b"QR-ONE\r", b"QR-ONE\r"], gap_s=0.05, settle_s=0.2)
        self.assertEqual(line.call_args_list, [call("QR-ONE"), call("QR-ONE")])

    def test_code_split_across_reads_is_reassembled(self) -> None:
        line, _ = self.read_chunks([b"WALLPAPER|oi=1", b"|art=A-1\r", b"\n"], gap_s=0.05)
        line.assert_called_once_with("WALLPAPER|oi=1|art=A-1")

    def test_code_without_terminator_is_flushed_after_silence(self) -> None:
        line, _ = self.read_chunks([b"QR-NO-SUFFIX"])
        line.assert_called_once_with("QR-NO-SUFFIX")

    def test_utf8_cyrillic_is_preserved(self) -> None:
        qr = "WALLPAPER|oi=21898|art=КРТ-003|lk=КРТ-003_PAINTING"
        line, error = self.read_once((qr + "\r\n").encode("utf-8"))
        line.assert_called_once_with(qr)
        error.assert_not_called()

    def test_wrong_encoding_rejects_whole_qr_instead_of_stripping_article(self) -> None:
        with self.assertLogs("scanner.com", level="ERROR"):
            line, error = self.read_once("WALLPAPER|art=КРТ-003\r\n".encode("cp1251"))
        line.assert_not_called()
        error.assert_called_once_with()

    def test_configured_cp1251_preserves_cyrillic(self) -> None:
        qr = "WALLPAPER|art=КРТ-003"
        line, error = self.read_once((qr + "\r\n").encode("cp1251"), "cp1251")
        line.assert_called_once_with(qr)
        error.assert_not_called()

    def test_scanner_encoding_config_defaults_and_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(json.dumps({"scanners": [
                {"device_id": "UTF", "com_port": "COM1"},
                {"device_id": "WIN", "com_port": "COM2", "encoding": "cp1251"},
            ]}), encoding="utf-8")
            config = load_config(path)
        self.assertEqual(config.scanners[0].encoding, "utf-8")
        self.assertEqual(config.scanners[1].encoding, "cp1251")

    def test_invalid_encoding_config_fails_before_starting_scanner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "config.json"
            path.write_text(json.dumps({"scanners": [
                {"device_id": "BAD", "com_port": "COM1", "encoding": "not-an-encoding"},
            ]}), encoding="utf-8")
            with self.assertRaises(LookupError):
                load_config(path)
