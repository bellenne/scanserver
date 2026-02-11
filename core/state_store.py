from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("state")


class StateStore:
    """
    Хранит per-device:
      - user_id
      - mode
    """
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"devices": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("Failed to load state file %s: %s", self.path, e)
            return {"devices": {}}

    def save(self, data: dict[str, Any]) -> None:
        try:
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning("Failed to save state file %s: %s", self.path, e)
