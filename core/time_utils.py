from __future__ import annotations

from datetime import datetime, timezone


def iso_now_local() -> str:
    # отдаёт ISO с таймзоной (локальная)
    return datetime.now().astimezone().isoformat(timespec="seconds")


def iso_now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
