import base64
import importlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Callable, Optional


_APP_DIR_NAME = "ADB Manager"


def _bundle_data_dir() -> Path:
    """Directory containing data shipped read-only with the application."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        return base / "data"
    return Path(__file__).parent.parent / "data"


def _asset_path(name: str) -> Path:
    """Locate an asset in source checkouts and in the frozen bundle."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        base = Path(__file__).parent.parent
    return base / "assets" / name


def _user_data_dir() -> Path:
    """Writable per-user directory for the standalone build."""
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
        return root / _APP_DIR_NAME
    if sys.platform.startswith("darwin"):
        return Path.home() / "Library" / "Application Support" / _APP_DIR_NAME
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / _APP_DIR_NAME


def _data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return _user_data_dir()
    return _bundle_data_dir()


DB_PATH = _data_dir() / "packages.json"
_SEED_DB_PATH = _bundle_data_dir() / "packages.json"

_USER_DB_PATH: Optional[Path] = None


def set_user_db_path(path: str) -> None:
    global _USER_DB_PATH, _cache, _cache_key
    _USER_DB_PATH = Path(path)
    _cache = None
    _cache_key = None


def _effective_path() -> Path:
    return _USER_DB_PATH or DB_PATH


_cache: Optional[dict[str, str]] = None
_cache_key: Optional[tuple[str, float]] = None


def _load() -> dict[str, str]:
    global _cache, _cache_key
    path = _effective_path()
    read_path = path
    # A frozen one-file build can run even if the per-user DB cannot be
    # created (e.g. an unwritable home directory); fall back to the bundled DB.
    if not read_path.exists() and _SEED_DB_PATH != path and _SEED_DB_PATH.exists():
        read_path = _SEED_DB_PATH
    try:
        key = (str(read_path), read_path.stat().st_mtime)
        if _cache is not None and key == _cache_key:
            return _cache
        with open(read_path, "r", encoding="utf-8") as f:
            _cache = json.load(f)
        _cache_key = key
        return _cache
    except Exception:
        _cache = {}
        _cache_key = None
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
        global _cache, _cache_key
        _cache = combined
        _cache_key = (str(save_path), save_path.stat().st_mtime)
        return True, msg
    except Exception as e:
        return False, str(e)


def ensure_db_exists() -> None:
    path = _effective_path()
    if path.exists():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    # The standalone build ships a seeded DB inside its temporary bundle.
    # Copy it into the writable per-user location so later updates persist.
    if _SEED_DB_PATH != path and _SEED_DB_PATH.exists():
        try:
            shutil.copyfile(_SEED_DB_PATH, path)
            return
        except OSError:
            pass

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


def _legacy_device_labels(raw: str) -> dict[str, str]:
    """Fallback for older Android versions that expose labels in dumpsys."""
    import re

    names: dict[str, str] = {}
    current_pkg: Optional[str] = None
    for line in raw.splitlines():
        m = re.match(r'\s*Package \[([^\]]+)\]', line)
        if m:
            current_pkg = m.group(1).strip()
            continue
        if not current_pkg:
            continue
        m2 = re.search(r'nonLocalizedLabel=(.+)', line)
        if not m2:
            continue
        label = m2.group(1).strip()
        if not label or label.lower() in ("null", "0"):
            continue
        if re.match(r"^0x[0-9a-fA-F]+$", label):
            continue
        names[current_pkg] = label
    return names


def _read_device_labels(on_progress: Optional[Callable[[str], None]] = None) -> tuple[dict[str, str], str]:
    """Read labels through PackageManager using a tiny bundled app_process dex."""
    import shlex
    from core.adb import exec_out

    dex = _asset_path("device_labels.dex")
    if not dex.is_file():
        return {}, f"Device label helper is missing: {dex}"

    remote = "/data/local/tmp/adb_manager_labels.dex"
    encoded = base64.b64encode(dex.read_bytes()).decode("ascii")
    # Write, run, and remove the helper in a single ADB round-trip.  Using
    # exec-out avoids a PTY and is noticeably faster than adb push + shell +
    # rm, especially over wireless ADB.  The dex is small (~2.5 KB).
    command = (
        f"printf '%s' {shlex.quote(encoded)} | base64 -d > {shlex.quote(remote)} && "
        f"CLASSPATH={shlex.quote(remote)} app_process /system/bin DeviceLabels; "
        f"rc=$?; rm -f {shlex.quote(remote)}; exit $rc"
    )
    if on_progress:
        on_progress("Reading app labels through Android PackageManager…")

    stdout, stderr, rc = exec_out(command, timeout=180)
    if rc != 0:
        detail = (stderr or stdout or "app_process label helper failed.").strip()
        return {}, detail

    names: dict[str, str] = {}
    for line in stdout.splitlines():
        if "\t" not in line:
            continue
        pkg, label = line.split("\t", 1)
        pkg, label = pkg.strip(), label.strip()
        if not pkg or not label:
            continue
        if label.lower() == "null" or label == pkg:
            continue
        names[pkg] = label
    return names, ""


def harvest_from_device(
    output_path: Optional[str] = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> tuple[int, str]:
    from core.adb import shell, is_connected

    if not is_connected():
        return 0, "No device connected."

    if on_progress:
        on_progress("Reading installed app labels from device…")

    device_names, helper_error = _read_device_labels(on_progress)
    if not device_names:
        # A transport timeout would only be repeated by the legacy dump, and
        # the dump has no labels on modern Android anyway.
        if helper_error and "timed out" in helper_error.lower():
            return 0, f"Could not harvest labels: {helper_error}"
        # Keep compatibility with older Android releases where PackageManager
        # labels were included in the package dump.
        if on_progress:
            on_progress("Trying the legacy dumpsys label reader…")
        stdout, stderr, rc = shell("dumpsys package packages", timeout=60)
        if rc == 0 and stdout:
            device_names = _legacy_device_labels(stdout)
        if not device_names:
            detail = helper_error or stderr or "No readable labels were reported."
            return 0, f"Could not harvest labels: {detail}"

    if on_progress:
        on_progress(f"Found {len(device_names):,} readable labels on device. Merging…")

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

    global _cache, _cache_key
    _cache = existing
    _cache_key = (str(save_path), save_path.stat().st_mtime)

    msg = (
        f"Found {len(device_names):,} labels on device "
        f"({added:,} new). DB now has {len(existing):,} entries."
    )
    if on_progress:
        on_progress(msg)
    return added, msg
