from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from core.config import load_config
from scanner.com_reader import ComReader


class ComReaderTests(unittest.TestCase):
    def read_once(self, raw: bytes, encoding: str = "utf-8") -> tuple[Mock, Mock]:
        on_line, on_error = Mock(), Mock()
        reader = ComReader("TEST", 9600, on_line, encoding=encoding, on_decode_error=on_error)
        reader._ser = Mock()

        def stop_after_line() -> bytes:
            reader._stop = True
            return raw

        reader._ser.readline.side_effect = stop_after_line
        reader._read_loop()
        return on_line, on_error

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
