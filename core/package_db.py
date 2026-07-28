import json
import os
import sys
import importlib
from typing import Optional, Callable
from pathlib import Path


def _data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "data"
    return Path(__file__).parent.parent / "data"


DB_PATH = _data_dir() / "packages.json"

_USER_DB_PATH: Optional[Path] = None


def set_user_db_path(path: str) -> None:
    global _USER_DB_PATH
    _USER_DB_PATH = Path(path)


def _effective_path() -> Path:
    if _USER_DB_PATH and _USER_DB_PATH.exists():
        return _USER_DB_PATH
    return DB_PATH


_cache: Optional[dict[str, str]] = None
_cache_mtime: float = 0.0


def _load() -> dict[str, str]:
    global _cache, _cache_mtime
    path = _effective_path()
    try:
        mtime = path.stat().st_mtime
        if _cache is not None and mtime == _cache_mtime:
            return _cache
        with open(path, "r", encoding="utf-8") as f:
            _cache = json.load(f)
        _cache_mtime = mtime
        return _cache
    except Exception:
        _cache = {}
        return _cache


def lookup(package: str) -> Optional[str]:
    return _load().get(package)


def lookup_all(packages: list[str]) -> dict[str, Optional[str]]:
    db = _load()
    return {p: db.get(p) for p in packages}


def db_size() -> int:
    return len(_load())


def db_path() -> str:
    return str(_effective_path())


def _get_collector():
    root = str(Path(__file__).parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module("collect_packages")


def collect(
    output_path: Optional[str] = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> tuple[bool, str]:
    save_path = Path(output_path) if output_path else _effective_path()
    save_path.parent.mkdir(parents=True, exist_ok=True)

    if on_progress:
        on_progress("Fetching UAD-NG and vendor package lists...")

    try:
        collector = _get_collector()
        combined = collector.collect(output_path=str(save_path), verbose=False)
        msg = f"Saved {len(combined):,} entries to {save_path}"
        if on_progress:
            on_progress(msg)
        global _cache, _cache_mtime
        _cache = combined
        _cache_mtime = save_path.stat().st_mtime
        return True, msg
    except Exception as e:
        return False, str(e)


def ensure_db_exists() -> None:
    path = _effective_path()
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        collector = _get_collector()
        seed = dict(collector.INLINE_PACKAGES)
    except Exception:
        seed = {}
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(seed, f, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception:
        pass


def harvest_from_device(
    output_path: Optional[str] = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> tuple[int, str]:
    import re
    from core.adb import shell, is_connected

    if not is_connected():
        return 0, "No device connected."

    if on_progress:
        on_progress("Pulling package list from device (dumpsys)…")

    stdout, stderr, rc = shell("dumpsys package packages", timeout=60)
    if rc != 0 or not stdout:
        return 0, f"dumpsys failed: {stderr}"

    device_names: dict[str, str] = {}
    current_pkg: Optional[str] = None
    for line in stdout.splitlines():
        m = re.match(r'\s*Package \[([^\]]+)\]', line)
        if m:
            current_pkg = m.group(1).strip()
            continue
        if current_pkg:
            m2 = re.search(r'nonLocalizedLabel=(.+)', line)
            if m2:
                label = m2.group(1).strip()
                if label and label.lower() not in ('null', '0', ''):
                    if not re.match(r'^0x[0-9a-fA-F]+$', label):
                        device_names[current_pkg] = label

    if on_progress:
        on_progress(f"Found {len(device_names):,} labels on device. Merging…")

    existing = _load()
    added = 0
    for pkg, label in device_names.items():
        if not existing.get(pkg):
            added += 1
        existing[pkg] = label

    save_path = Path(output_path) if output_path else _effective_path()
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2, sort_keys=True)

    global _cache, _cache_mtime
    _cache = existing
    _cache_mtime = save_path.stat().st_mtime

    msg = f"Harvested {len(device_names):,} labels from device ({added:,} new). DB now has {len(existing):,} entries."
    if on_progress:
        on_progress(msg)
    return added, msg
