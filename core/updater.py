from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from core.config import UpdaterConfig

log = logging.getLogger("updater")


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    asset: ReleaseAsset


def try_update_from_github(cfg: UpdaterConfig, app_dir: Path) -> bool:
    if not cfg.enabled or not cfg.check_on_startup:
        return False
    if not getattr(sys, "frozen", False):
        log.info("Auto-update skipped: not running as packaged executable")
        return False
    if not cfg.github_owner or not cfg.github_repo:
        log.info("Auto-update skipped: github_owner/github_repo are not configured")
        return False

    try:
        release = _fetch_release_info(cfg)
    except Exception as e:
        log.warning("Auto-update check failed: %s", e)
        return False

    if release is None:
        return False

    if not _is_newer_version(release.version, cfg.current_version):
        log.info("No update available. Current=%s Latest=%s", cfg.current_version, release.version)
        return False

    try:
        _download_and_schedule_update(cfg=cfg, release=release, app_dir=app_dir)
    except Exception as e:
        log.warning("Failed to prepare auto-update: %s", e)
        return False

    return True


def _fetch_release_info(cfg: UpdaterConfig) -> ReleaseInfo | None:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ScanServer-Updater"}
    if cfg.github_token:
        headers["Authorization"] = f"Bearer {cfg.github_token}"

    with httpx.Client(timeout=20.0, headers=headers, follow_redirects=True) as client:
        if cfg.allow_prerelease:
            url = f"https://api.github.com/repos/{cfg.github_owner}/{cfg.github_repo}/releases"
            resp = client.get(url)
            resp.raise_for_status()
            releases = resp.json()
            if not isinstance(releases, list):
                raise ValueError("Unexpected GitHub releases response")
            release_data = next((r for r in releases if not r.get("draft")), None)
        else:
            url = f"https://api.github.com/repos/{cfg.github_owner}/{cfg.github_repo}/releases/latest"
            resp = client.get(url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            release_data = resp.json()

    if not release_data:
        return None

    tag_name = str(release_data.get("tag_name", "")).strip()
    version = _normalize_version(tag_name)
    if not version:
        raise ValueError("GitHub release tag_name is empty")

    assets = release_data.get("assets") or []
    if not isinstance(assets, list):
        raise ValueError("Unexpected GitHub release assets format")

    asset = _pick_asset(cfg, assets)
    if asset is None:
        raise ValueError("No matching zip asset found in the GitHub release")

    return ReleaseInfo(version=version, asset=asset)


def _pick_asset(cfg: UpdaterConfig, assets: list[dict[str, Any]]) -> ReleaseAsset | None:
    for asset in assets:
        name = str(asset.get("name", "")).strip()
        url = str(asset.get("browser_download_url", "")).strip()
        if not name or not url:
            continue
        if cfg.asset_name:
            if name == cfg.asset_name:
                return ReleaseAsset(name=name, url=url)
            continue
        if name.lower().endswith(".zip"):
            return ReleaseAsset(name=name, url=url)
    return None


def _normalize_version(version: str) -> str:
    v = str(version or "").strip()
    if v.lower().startswith("v"):
        v = v[1:]
    return v.strip()


def _version_tuple(version: str) -> tuple[int, ...]:
    cleaned = _normalize_version(version)
    if not cleaned:
        return (0,)

    parts: list[int] = []
    for chunk in cleaned.replace("-", ".").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts or [0])


def _is_newer_version(remote: str, current: str) -> bool:
    return _version_tuple(remote) > _version_tuple(current)


def _download_and_schedule_update(cfg: UpdaterConfig, release: ReleaseInfo, app_dir: Path) -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="scanserver-update-"))
    zip_path = temp_root / release.asset.name
    extract_dir = temp_root / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)

    headers = {"User-Agent": "ScanServer-Updater"}
    if cfg.github_token:
        headers["Authorization"] = f"Bearer {cfg.github_token}"

    with httpx.Client(timeout=120.0, headers=headers, follow_redirects=True) as client:
        with client.stream("GET", release.asset.url) as resp:
            resp.raise_for_status()
            with zip_path.open("wb") as f:
                for chunk in resp.iter_bytes():
                    if chunk:
                        f.write(chunk)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    source_dir = _locate_release_dir(extract_dir, cfg.executable_name)
    if source_dir is None:
        raise FileNotFoundError(f"Could not find {cfg.executable_name} inside the update archive")

    _write_update_script(cfg=cfg, source_dir=source_dir, app_dir=app_dir)


def _locate_release_dir(extract_dir: Path, executable_name: str) -> Path | None:
    direct = extract_dir / executable_name
    if direct.exists():
        return extract_dir

    for candidate in extract_dir.rglob(executable_name):
        if candidate.is_file():
            return candidate.parent

    return None


def _write_update_script(cfg: UpdaterConfig, source_dir: Path, app_dir: Path) -> None:
    current_pid = os.getpid()
    exe_path = app_dir / cfg.executable_name
    script_path = app_dir / "apply_update.cmd"

    xf = " ".join(f'"{name}"' for name in cfg.preserve_files)
    xd = " ".join(f'"{name}"' for name in cfg.preserve_dirs)

    lines = [
        "@echo off",
        "setlocal enableextensions",
        f'set "SOURCE_DIR={source_dir}"',
        f'set "TARGET_DIR={app_dir}"',
        f'set "APP_EXE={exe_path}"',
        f'set "WAIT_PID={current_pid}"',
        ":wait_loop",
        'tasklist /FI "PID eq %WAIT_PID%" | find "%WAIT_PID%" >nul',
        "if not errorlevel 1 (",
        "  timeout /t 1 /nobreak >nul",
        "  goto wait_loop",
        ")",
    ]

    robocopy_line = 'robocopy "%SOURCE_DIR%" "%TARGET_DIR%" /E /R:2 /W:1 /NFL /NDL /NJH /NJS /NP'
    if xf:
        robocopy_line += f" /XF {xf}"
    if xd:
        robocopy_line += f" /XD {xd}"
    lines.append(robocopy_line)
    lines.append('start "" "%APP_EXE%"')
    lines.append("endlocal")

    script_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    subprocess.Popen(["cmd", "/c", str(script_path)], cwd=str(app_dir), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
