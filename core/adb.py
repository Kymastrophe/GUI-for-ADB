import subprocess
import shutil
import re
import sys
import os
from typing import Optional


def _find_adb() -> str:
    path = shutil.which("adb")
    if path:
        return path
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
        for candidate in ["adb", "adb.exe"]:
            full = os.path.join(base, candidate)
            if os.path.isfile(full):
                return full
    return "adb"

ADB = _find_adb()


def run(args: list[str], timeout: int = 30) -> tuple[str, str, int]:
    try:
        result = subprocess.run(
            [ADB] + args,
            capture_output=True, text=True,
            timeout=timeout
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "ADB command timed out.", 1
    except FileNotFoundError:
        return "", f"ADB binary not found at: {ADB}", 1
    except Exception as e:
        return "", str(e), 1


def shell(cmd: str, timeout: int = 30) -> tuple[str, str, int]:
    return run(["shell", cmd], timeout=timeout)


def su_shell(cmd: str, timeout: int = 30) -> tuple[str, str, int]:
    variant = _get_su_variant(timeout=timeout)
    if variant is None:
        return "", "Root not available on this device (su not found or not granted).", 1
    escaped = cmd.replace('"', '\\"').replace("'", "'\\''")
    return shell(variant.format(cmd=escaped), timeout=timeout)


# None = not yet probed, str = working template, False = no root
_su_variant_cache: "str | None | bool" = None

_SU_VARIANTS = [
    'su -c "{cmd}"',
    'su 0 sh -c "{cmd}"',
    'su 0 -c "{cmd}"',
    'su root sh -c "{cmd}"',
    'su root -c "{cmd}"',
]

_NO_ROOT_PHRASES = (
    "not found", "inaccessible", "permission denied",
    "no such file", "command not found",
)


def _get_su_variant(timeout: int = 10) -> "str | None":
    global _su_variant_cache
    if _su_variant_cache is not None:
        return None if _su_variant_cache is False else _su_variant_cache  # type: ignore[return-value]

    for variant in _SU_VARIANTS:
        stdout, stderr, rc = shell(variant.format(cmd="id"), timeout=timeout)
        combined = (stdout + stderr).lower()

        if "uid=0" in combined:
            _su_variant_cache = variant
            return variant

        if any(phrase in combined for phrase in _NO_ROOT_PHRASES):
            _su_variant_cache = False
            return None

        if rc == 0 and not any(w in combined for w in ("invalid", "error", "usage", "unknown")):
            _su_variant_cache = variant
            return variant

    _su_variant_cache = False
    return None


def reset_su_cache() -> None:
    global _su_variant_cache
    _su_variant_cache = None


def devices() -> list[dict]:
    stdout, _, _ = run(["devices"])
    result = []
    for line in stdout.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) == 2:
            result.append({"serial": parts[0], "state": parts[1]})
    return result


def is_connected() -> bool:
    return any(d["state"] == "device" for d in devices())


def connect(host: str, port: int = 5555) -> tuple[bool, str]:
    stdout, stderr, rc = run(["connect", f"{host}:{port}"])
    ok = "connected" in stdout.lower()
    if ok:
        reset_su_cache()
    return ok, stdout or stderr


def disconnect_all() -> str:
    stdout, _, _ = run(["disconnect"])
    return stdout


def pair(host: str, port: int, code: str) -> tuple[bool, str]:
    stdout, stderr, rc = run(["pair", f"{host}:{port}", code], timeout=60)
    ok = rc == 0 and "successfully" in stdout.lower()
    return ok, stdout or stderr


def list_packages(include_system: bool = True) -> list[str]:
    cmd = "pm list packages" if include_system else "pm list packages -3"
    stdout, _, rc = shell(cmd)
    if rc != 0:
        return []
    pkgs = []
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            pkgs.append(line[8:])
    return sorted(pkgs)


def get_package_info(package: str) -> dict:
    stdout, _, _ = shell(f"dumpsys package {package}")
    info = {"package": package, "version": "?", "enabled": True, "installer": "?"}
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("versionName="):
            info["version"] = line.split("=", 1)[1]
        elif "enabled=" in line:
            info["enabled"] = "false" not in line.lower()
        elif line.startswith("installerPackageName="):
            info["installer"] = line.split("=", 1)[1]
    return info


def uninstall_package(package: str, keep_data: bool = False) -> tuple[bool, str]:
    flag = "--keep-data " if keep_data else ""
    stdout, stderr, rc = shell(f"pm uninstall {flag}{package}")
    if rc == 0 and "success" in stdout.lower():
        return True, stdout
    stdout2, stderr2, rc2 = su_shell(f"pm uninstall {package}")
    ok = rc2 == 0 and "success" in stdout2.lower()
    return ok, stdout2 or stderr2 or stderr


def uninstall_for_user(package: str) -> tuple[bool, str]:
    stdout, stderr, rc = shell(f"pm uninstall -k --user 0 {package}")
    ok = rc == 0 and "success" in (stdout + stderr).lower()
    return ok, stdout or stderr


def reinstall_for_user(package: str) -> tuple[bool, str]:
    stdout, stderr, rc = shell(f"pm install-existing --user 0 {package}")
    ok = rc == 0 and "installed" in (stdout + stderr).lower()
    return ok, stdout or stderr


def disable_package(package: str) -> tuple[bool, str]:
    stdout, stderr, rc = shell(f"pm disable-user --user 0 {package}")
    if rc == 0 and "disabled" in (stdout + stderr).lower():
        return True, stdout or stderr
    stdout2, stderr2, rc2 = su_shell(f"pm disable-user --user 0 {package}")
    ok = rc2 == 0 and "disabled" in (stdout2 + stderr2).lower()
    return ok, stdout2 or stderr2 or stdout or stderr


def enable_package(package: str) -> tuple[bool, str]:
    stdout, stderr, rc = shell(f"pm enable --user 0 {package}")
    if rc == 0 and "enabled" in (stdout + stderr).lower():
        return True, stdout or stderr
    stdout2, stderr2, rc2 = su_shell(f"pm enable --user 0 {package}")
    ok = rc2 == 0
    return ok, stdout2 or stderr2 or stdout or stderr


def hide_package(package: str) -> tuple[bool, str]:
    stdout, stderr, rc = shell(f"pm hide --user 0 {package}")
    ok = rc == 0 and "hidden" in (stdout + stderr).lower()
    return ok, stdout or stderr


def unhide_package(package: str) -> tuple[bool, str]:
    stdout, stderr, rc = shell(f"pm unhide --user 0 {package}")
    ok = rc == 0
    return ok, stdout or stderr


def suspend_package(package: str) -> tuple[bool, str]:
    stdout, stderr, rc = shell(f"pm suspend --user 0 {package}")
    ok = rc == 0 and "suspended" in (stdout + stderr).lower()
    return ok, stdout or stderr


def unsuspend_package(package: str) -> tuple[bool, str]:
    stdout, stderr, rc = shell(f"pm unsuspend --user 0 {package}")
    ok = rc == 0
    return ok, stdout or stderr


def force_stop(package: str) -> tuple[bool, str]:
    stdout, stderr, rc = shell(f"am force-stop {package}")
    return rc == 0, stdout or stderr


def get_monitor_snapshot(prev: "dict | None" = None) -> dict:
    COMPOUND = (
        "echo '===MEMINFO==='; cat /proc/meminfo; "
        "echo '===STAT==='; cat /proc/stat; "
        "echo '===PS==='; ps -A -o USER,PID,PPID,RSS,S,NAME 2>/dev/null || ps -A"
    )
    raw, _, _ = shell(COMPOUND, timeout=20)

    sections: dict[str, str] = {}
    current = ""
    buf: list[str] = []
    for line in raw.splitlines():
        if line.startswith("===") and line.endswith("==="):
            if current:
                sections[current] = "\n".join(buf)
            current = line.strip("=")
            buf = []
        else:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf)

    total_kb = avail_kb = free_kb = 0
    for line in sections.get("MEMINFO", "").splitlines():
        try:
            if line.startswith("MemTotal:"):
                total_kb = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                avail_kb = int(line.split()[1])
            elif line.startswith("MemFree:"):
                free_kb = int(line.split()[1])
        except (IndexError, ValueError):
            pass
    used_kb = total_kb - (avail_kb or free_kb)
    mem_pct = round(used_kb / total_kb * 100, 1) if total_kb else 0.0

    cpu_idle = cpu_total = 0
    for line in sections.get("STAT", "").splitlines():
        if line.startswith("cpu "):
            try:
                vals = [int(v) for v in line.split()[1:]]
                cpu_total = sum(vals)
                cpu_idle = vals[3] if len(vals) > 3 else 0
            except (ValueError, IndexError):
                pass
            break

    cpu_pct = 0.0
    if prev and "cpu_total" in prev:
        d_total = cpu_total - prev["cpu_total"]
        d_idle = cpu_idle - prev["cpu_idle"]
        if d_total > 0:
            cpu_pct = round((1 - d_idle / d_total) * 100, 1)

    procs: list[dict] = []
    ps_lines = sections.get("PS", "").splitlines()
    if ps_lines:
        header = ps_lines[0].strip().upper()
        use_custom = "RSS" in header and "VSZ" not in header
        for line in ps_lines[1:]:
            parts = line.split()
            try:
                if use_custom:
                    if len(parts) < 6:
                        continue
                    user, pid, ppid = parts[0], parts[1], parts[2]
                    rss, state, name = int(parts[3]), parts[4], parts[-1]
                else:
                    if len(parts) < 9:
                        continue
                    user, pid, ppid = parts[0], parts[1], parts[2]
                    rss, state, name = int(parts[4]), parts[7], parts[-1]

                procs.append({
                    "user":    user,
                    "pid":     pid,
                    "ppid":    ppid,
                    "state":   state,
                    "mem_kb":  rss,
                    "mem_mb":  round(rss / 1024, 1),
                    "mem_pct": round(rss / total_kb * 100, 2) if total_kb else 0.0,
                    "name":    name,
                })
            except (IndexError, ValueError):
                continue

    procs.sort(key=lambda p: p["mem_kb"], reverse=True)

    return {
        "stats": {
            "total_ram_kb": total_kb,
            "used_ram_kb":  used_kb,
            "mem_pct":      mem_pct,
            "cpu_pct":      cpu_pct,
        },
        "procs": procs,
        "raw_proc_stats": {"cpu_idle": cpu_idle, "cpu_total": cpu_total},
    }


def kill_process(pid: str, use_root: bool = False) -> tuple[bool, str]:
    cmd = f"kill -9 {pid}"
    if use_root:
        stdout, stderr, rc = su_shell(cmd)
    else:
        stdout, stderr, rc = shell(cmd)
    return rc == 0, stdout or stderr


def reboot(mode: str = "") -> tuple[bool, str]:
    args = ["reboot"]
    if mode:
        args.append(mode)
    stdout, stderr, rc = run(args, timeout=10)
    return rc == 0, stdout or stderr


def get_prop(prop: str) -> str:
    stdout, _, _ = shell(f"getprop {prop}")
    return stdout.strip()


def device_info() -> dict:
    return {
        "model":   get_prop("ro.product.model"),
        "brand":   get_prop("ro.product.brand"),
        "android": get_prop("ro.build.version.release"),
        "sdk":     get_prop("ro.build.version.sdk"),
        "serial":  get_prop("ro.serialno"),
        "build":   get_prop("ro.build.display.id"),
    }


def has_root() -> bool:
    stdout, _, rc = su_shell("id")
    return rc == 0 and "uid=0" in stdout


def list_dir(path: str) -> list[dict]:
    stdout, stderr, rc = su_shell(f"ls -la {path}")
    if rc != 0:
        stdout, stderr, rc = shell(f"ls -la {path}")
    entries = []
    for line in stdout.splitlines():
        parts = line.split(None, 8)
        if len(parts) < 8:
            continue
        perms = parts[0]
        if not perms or perms[0] not in ('d', '-', 'l', 'c', 'b', 's', 'p'):
            continue
        size = parts[4]
        raw_name = parts[-1]
        if " -> " in raw_name:
            raw_name = raw_name.split(" -> ")[0].strip()
        name = raw_name
        if name in (".", "..") or not name:
            continue
        entries.append({
            "perms":  perms,
            "size":   size,
            "name":   name,
            "is_dir": perms.startswith("d") or perms.startswith("l"),
        })
    return entries


def _normalize_android_path(path: str) -> str:
    path = re.sub(r"^/mnt/user/\d+/emulated/(\d+)", r"/storage/emulated/\1", path)
    path = re.sub(r"^/mnt/runtime/\w+/emulated/(\d+)", r"/storage/emulated/\1", path)
    path = re.sub(r"^/storage/self/primary(?=/|$)", "/sdcard", path)
    return path


def pull_file(remote: str, local: str) -> tuple[bool, str]:
    remote = _normalize_android_path(remote)
    stdout, stderr, rc = run(["pull", remote, local], timeout=120)
    return rc == 0, stdout or stderr


def push_file(local: str, remote: str) -> tuple[bool, str]:
    remote = _normalize_android_path(remote)
    stdout, stderr, rc = run(["push", local, remote], timeout=120)
    return rc == 0, stdout or stderr


def delete_file(path: str, use_root: bool = True) -> tuple[bool, str]:
    cmd = f"rm -rf {path}"
    if use_root:
        return su_shell(cmd)
    return shell(cmd)
