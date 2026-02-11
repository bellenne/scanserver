from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from api.client import ApiClient

log = logging.getLogger("users_cache")


@dataclass(frozen=True)
class UsersSnapshot:
    ts: float
    users: list[dict]


class UsersCache:
    def __init__(self, api: ApiClient, cache_file: Path, ttl_s: int = 300) -> None:
        self.api = api
        self.cache_file = cache_file
        self.ttl_s = ttl_s
        self._mem: UsersSnapshot | None = None

    def get(self) -> list[dict]:
        now = time.time()

        if self._mem and now - self._mem.ts <= self.ttl_s:
            return self._mem.users

        snap = self._read_disk()
        if snap and now - snap.ts <= self.ttl_s:
            self._mem = snap
            return snap.users

        users = self.api.get_users()
        self._mem = UsersSnapshot(ts=now, users=users)
        self._write_disk(self._mem)
        return users

    def _read_disk(self) -> UsersSnapshot | None:
        if not self.cache_file.exists():
            return None
        try:
            data = json.loads(self.cache_file.read_text(encoding="utf-8"))
            return UsersSnapshot(ts=float(data["ts"]), users=list(data["users"]))
        except Exception as e:
            log.warning("Failed to read users cache: %s", e)
            return None

    def _write_disk(self, snap: UsersSnapshot) -> None:
        try:
            self.cache_file.write_text(
                json.dumps({"ts": snap.ts, "users": snap.users}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            log.warning("Failed to write users cache: %s", e)
