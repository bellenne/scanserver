from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ModeName = Literal["COMPARE_FILL", "DEFECT", "TRANSFER", "TRANSFER_DEFECT"]


@dataclass(frozen=True)
class SvcUser:
    user_id: int


@dataclass(frozen=True)
class SvcMode:
    mode: ModeName


SvcCommand = SvcUser | SvcMode


def parse_svc(line: str) -> SvcCommand | None:
    # SVC:USER:{id}
    # SVC:MODE:COMPARE_FILL
    if not line.startswith("SVC:"):
        return None

    parts = line.split(":")
    if len(parts) < 3:
        return None

    kind = parts[1].strip().upper()

    if kind == "USER":
        try:
            uid = int(parts[2])
            return SvcUser(user_id=uid)
        except Exception:
            return None

    if kind == "MODE":
        m = parts[2].strip().upper()
        if m in ("COMPARE_FILL", "DEFECT", "TRANSFER", "TRANSFER_DEFECT"):
            return SvcMode(mode=m)  # type: ignore[arg-type]
        return None

    return None
