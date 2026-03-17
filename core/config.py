from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.app_meta import APP_NAME, APP_VERSION


@dataclass(frozen=True)
class ScannerConfig:
    device_id: str
    com_port: str
    baudrate: int = 9600


@dataclass(frozen=True)
class Endpoints:
    events: str = "/api/v1/cut/scan"
    transfer: str = "/api/v1/transfer/scan"
    defect: str = "/api/v1/defects/"
    package: str = "/api/v1/package/scan"


@dataclass(frozen=True)
class UpdaterConfig:
    enabled: bool = False
    check_on_startup: bool = True
    current_version: str = APP_VERSION
    github_owner: str = ""
    github_repo: str = ""
    github_token: str | None = None
    asset_name: str = ""
    allow_prerelease: bool = False
    executable_name: str = f"{APP_NAME}.exe"
    preserve_files: tuple[str, ...] = ("config.json", "state.json", "users_cache.json")
    preserve_dirs: tuple[str, ...] = (".tts_cache",)


@dataclass(frozen=True)
class AppConfig:
    env: str
    base_url: str
    http_timeout_s: float
    state_file: str
    users_cache_file: str
    users_cache_ttl_s: int
    tts_prefer_edge: bool
    tts_edge_voice: str
    tts_pyttsx3_voice_name: str | None
    tts_rate: int
    tts_volume: float
    scanners: list[ScannerConfig]
    endpoints: Endpoints
    updater: UpdaterConfig


def load_config(path: Path) -> AppConfig:
    raw: dict[str, Any] = {}
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))

    env = str(raw.get("env", "dev")).lower()
    dev_url = "http://localhost:8000"
    prod_url = "https://customcraft-mes.ru"
    base_url = str(raw.get("base_url", dev_url if env == "dev" else prod_url)).rstrip("/")

    endpoints_raw = raw.get("endpoints", {}) or {}
    endpoints = Endpoints(
        events=str(endpoints_raw.get("events", Endpoints.events)),
        transfer=str(endpoints_raw.get("transfer", Endpoints.transfer)),
        defect=str(endpoints_raw.get("defect", Endpoints.defect)),
        package=str(endpoints_raw.get("package", Endpoints.package)),
    )

    scanners_raw = raw.get("scanners", []) or []
    scanners: list[ScannerConfig] = []
    for s in scanners_raw:
        scanners.append(
            ScannerConfig(
                device_id=str(s["device_id"]),
                com_port=str(s["com_port"]),
                baudrate=int(s.get("baudrate", 9600)),
            )
        )

    updater_raw = raw.get("updater", {}) or {}
    updater = UpdaterConfig(
        enabled=bool(updater_raw.get("enabled", False)),
        check_on_startup=bool(updater_raw.get("check_on_startup", True)),
        current_version=APP_VERSION,
        github_owner=str(updater_raw.get("github_owner", "")).strip(),
        github_repo=str(updater_raw.get("github_repo", "")).strip(),
        github_token=(str(updater_raw.get("github_token", "")).strip() or None),
        asset_name=str(updater_raw.get("asset_name", "")).strip(),
        allow_prerelease=bool(updater_raw.get("allow_prerelease", False)),
        executable_name=str(updater_raw.get("executable_name", f"{APP_NAME}.exe")).strip() or f"{APP_NAME}.exe",
        preserve_files=tuple(str(x).strip() for x in (updater_raw.get("preserve_files", ["config.json", "state.json", "users_cache.json"]) or []) if str(x).strip()),
        preserve_dirs=tuple(str(x).strip() for x in (updater_raw.get("preserve_dirs", [".tts_cache"]) or []) if str(x).strip()),
    )

    return AppConfig(
        env=env,
        base_url=base_url,
        http_timeout_s=float(raw.get("http_timeout_s", 8.0)),
        state_file=str(raw.get("state_file", "state.json")),
        users_cache_file=str(raw.get("users_cache_file", "users_cache.json")),
        users_cache_ttl_s=int(raw.get("users_cache_ttl_s", 300)),
        tts_prefer_edge=bool(raw.get("tts_prefer_edge", True)),
        tts_edge_voice=str(raw.get("tts_edge_voice", "ru-RU-DmitryNeural")),
        tts_pyttsx3_voice_name=raw.get("tts_pyttsx3_voice_name", None),
        tts_rate=int(raw.get("tts_rate", 190)),
        tts_volume=float(raw.get("tts_volume", 1.0)),
        scanners=scanners,
        endpoints=endpoints,
        updater=updater,
    )
