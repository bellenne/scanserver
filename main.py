from __future__ import annotations

import signal
import sys
from pathlib import Path

from core.config import load_config
from core.logging_setup import setup_logging
from core.state_store import StateStore
from tts.manager import TTSManager
from api.client import ApiClient
from api.users_cache import UsersCache
from scanner.manager import ScannerManager

def app_dir() -> Path:
    # если exe
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # если обычный python запуск
    return Path.cwd()

def p_near_exe(name: str) -> Path:
    return app_dir() / name

def main() -> int:
    setup_logging()

    cfg = load_config(p_near_exe("config.json"))
    state = StateStore(p_near_exe(Path(cfg.state_file).name))
    state_data = state.load()

    api = ApiClient(base_url=cfg.base_url, timeout_s=cfg.http_timeout_s)
    users_cache = UsersCache(
        api=api,
        cache_file=p_near_exe(Path(cfg.users_cache_file).name),
        ttl_s=cfg.users_cache_ttl_s,
    )

    tts = TTSManager(
        prefer_edge=cfg.tts_prefer_edge,
        edge_voice=cfg.tts_edge_voice,
        pyttsx3_voice_name=cfg.tts_pyttsx3_voice_name,
        rate=cfg.tts_rate,
        volume=cfg.tts_volume,
    )
    tts.start()

    mgr = ScannerManager(
        api=api,
        users_cache=users_cache,
        tts=tts,
        state=state,
        initial_state=state_data,
        scanners=cfg.scanners,
        endpoints=cfg.endpoints,
    )

    def _shutdown(*_args):
        mgr.stop()
        tts.stop()
        return None

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    mgr.start()
    mgr.wait()
    print("ScanServer stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
