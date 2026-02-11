from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class Mode(Protocol):
    def on_scan(self, session: "ScannerSession", payload: str) -> None: ...


@dataclass
class ModeBase:
    name: str

    def on_scan(self, session: "ScannerSession", payload: str) -> None:
        raise NotImplementedError
