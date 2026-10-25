import os
import re
import shlex
import shutil
import subprocess
import sys


def _find_adb() -> str:
    path = shutil.which("adb")
    if path:
        return path

    # Look next to the package (source checkout) and the executable (frozen).
    candidates = [
        os.path.dirname(os.path.abspath(__file__)),
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ]
    if getattr(sys, "frozen", False):
        candidates.append(sys._MEIPASS)
        candidates.append(os.path.dirname(os.path.abspath(sys.executable)))

    names = ("adb.exe", "adb") if sys.platform.startswith("win") else ("adb", "adb.exe")
    for base in candidates:
        for name in names:
            full = os.path.join(base, name)
            if os.path.isfile(full) and (
                sys.platform.startswith("win") or os.access(full, os.X_OK)
            ):
                return full
    return "adb"

ADB = _find_adb()

_BATTERY_STATUS = {
    1: "Unknown",
    2: "Charging",
    3: "Discharging",
    4: "Not charging",
    5: "Full",
}
_BATTERY_HEALTH = {
    1: "Unknown",
    2: "Good",
    3: "Overheat",
    4: "Dead",
    5: "Over voltage",
    6: "Unspecified failure",
    7: "Cold",
}
_EOL_REMARKS = {
    0: "not defined",
    1: "normal",
    2: "warning — 80% consumed",
    3: "urgent — 90% consumed",
}


def run(args: list[str], timeout: int = 30) -> tuple[str, str, int]:
    try:
        result = subprocess.run(
            [ADB] + args,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
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


def exec_out(cmd: str, timeout: int = 30) -> tuple[str, str, int]:
    """Run a command without a PTY (faster for binary/text output)."""
    return run(["exec-out", cmd], timeout=timeout)


def su_shell(cmd: str, timeout: int = 30) -> tuple[str, str, int]:
    variant = _get_su_variant(timeout=timeout)
    if variant is None:
        return "", "Root not available on this device (su not found or not granted).", 1
    return shell(variant.format(cmd=shlex.quote(cmd)), timeout=timeout)


# None = not yet probed, str = working template, False = no root
_su_variant_cache: "str | None | bool" = None

_SU_VARIANTS = [
    "su -c {cmd}",
    "su 0 sh -c {cmd}",
    "su 0 -c {cmd}",
    "su root sh -c {cmd}",
    "su root -c {cmd}",
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
        stdout, stderr, rc = shell(variant.format(cmd=shlex.quote("id")), timeout=timeout)
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


def devices(timeout: int = 30) -> list[dict]:
    stdout, _, _ = run(["devices"], timeout=timeout)
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
    reset_su_cache()
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
        "echo '===PS==='; ps -A -o USER,PID,PPID,RSS,S,NAME 2>/dev/null || ps -A; "
        "echo '===PSTAT==='; cat /proc/[0-9]*/stat 2>/dev/null"
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

    proc_ticks: dict[str, int] = {}
    for line in sections.get("PSTAT", "").splitlines():
        try:
            pid = line.split(None, 1)[0]
            if not pid.isdigit():
                continue
            # comm (field 2) may contain spaces and parentheses; fields after
            # the final ')' start with state (field 3).  utime/stime are
            # fields 14/15, i.e. indexes 11/12 in that tail.
            tail = line[line.rfind(")") + 2:].split()
            if len(tail) < 13:
                continue
            proc_ticks[pid] = int(tail[11]) + int(tail[12])
        except (IndexError, ValueError):
            continue

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

    prev_ticks = (prev or {}).get("proc_ticks", {})
    d_total = cpu_total - prev.get("cpu_total", cpu_total) if prev else 0
    for p in procs:
        if not prev or d_total <= 0:
            p["cpu_pct"] = None
            continue
        pid = p["pid"]
        current = proc_ticks.get(pid)
        previous = prev_ticks.get(pid)
        if current is None or previous is None or current < previous:
            p["cpu_pct"] = 0.0
        else:
            # Normalised to all cores, matching the global CPU card.
            p["cpu_pct"] = round((current - previous) / d_total * 100, 1)

    procs.sort(key=lambda p: p["mem_kb"], reverse=True)

    return {
        "stats": {
            "total_ram_kb": total_kb,
            "used_ram_kb":  used_kb,
            "mem_pct":      mem_pct,
            "cpu_pct":      cpu_pct,
        },
        "procs": procs,
        "raw_proc_stats": {
            "cpu_idle": cpu_idle,
            "cpu_total": cpu_total,
            "proc_ticks": proc_ticks,
        },
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


def _getprop_map() -> dict[str, str]:
    """Return all system properties in one ADB round-trip."""
    stdout, _, _ = shell("getprop", timeout=15)
    props: dict[str, str] = {}
    for line in stdout.splitlines():
        m = re.match(r"\[([^\]]+)\]: \[(.*)\]$", line)
        if m:
            props[m.group(1)] = m.group(2)
    return props


_DEVICE_INFO_PROPS = {
    "brand":          "ro.product.brand",
    "model":          "ro.product.model",
    "device":         "ro.product.device",
    "board":          "ro.product.board",
    "android":        "ro.build.version.release",
    "sdk":            "ro.build.version.sdk",
    "security_patch": "ro.build.version.security_patch",
    "abi":            "ro.product.cpu.abi",
    "serial":         "ro.serialno",
    "build":          "ro.build.display.id",
    "build_type":     "ro.build.type",
}


def device_info(props: "dict[str, str] | None" = None) -> dict:
    props = props if props is not None else _getprop_map()
    return {key: props.get(prop, "") for key, prop in _DEVICE_INFO_PROPS.items()}


def _parse_int(value: "str | int | None") -> "int | None":
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def battery_info(raw: "str | None" = None) -> dict:
    """Parse ``dumpsys battery`` into display-ready values."""
    if raw is None:
        raw, stderr, rc = shell("dumpsys battery", timeout=15)
        if rc != 0:
            return {"available": False, "error": stderr or "dumpsys battery failed"}

    fields: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip().lower()] = value.strip()

    if not fields:
        return {"available": False, "error": "No battery data reported."}

    status_code = _parse_int(fields.get("status"))
    health_code = _parse_int(fields.get("health"))
    level = _parse_int(fields.get("level"))
    scale = _parse_int(fields.get("scale")) or 100
    percentage = round(level * 100 / scale) if level is not None else None

    power_source = "Battery"
    for field, label in (
        ("ac powered", "AC charger"),
        ("usb powered", "USB"),
        ("wireless powered", "Wireless"),
        ("dock powered", "Dock"),
    ):
        if fields.get(field, "").lower() == "true":
            power_source = label
            break

    voltage_mv = _parse_int(fields.get("voltage"))
    temperature_raw = _parse_int(fields.get("temperature"))
    charge_counter_ua = _parse_int(fields.get("charge counter"))
    max_capacity_ua = _parse_int(fields.get("maximum capacity"))
    design_capacity_ua = _parse_int(fields.get("design capacity"))

    def _mah(value: "int | None") -> "float | None":
        return round(value / 1000, 0) if value and value > 0 else None

    status = _BATTERY_STATUS.get(status_code, "Not reported")
    if status_code is not None and status_code not in _BATTERY_STATUS:
        status = f"Unknown (code {status_code})"
    health = _BATTERY_HEALTH.get(health_code, "Not reported")
    if health_code is not None and health_code not in _BATTERY_HEALTH:
        health = f"Unknown (code {health_code})"

    return {
        "available": True,
        "raw": raw,
        "level": percentage,
        "status_code": status_code,
        "status": status,
        "health_code": health_code,
        "health": health,
        "power_source": power_source,
        "voltage_mv": voltage_mv,
        "temperature_c": round(temperature_raw / 10, 1) if temperature_raw is not None else None,
        "technology": fields.get("technology") or "Not reported",
        "charge_counter_mah": _mah(charge_counter_ua),
        "max_capacity_mah": _mah(max_capacity_ua),
        "design_capacity_mah": _mah(design_capacity_ua),
    }


def _life_time_note(code: "int | None") -> str:
    if code is None:
        return "not reported"
    if code == 0:
        return "not defined"
    if 1 <= code <= 10:
        low = (code - 1) * 10
        high = code * 10
        return f"{low}–{high}% used, {100 - high}–{100 - low}% health remaining"
    if code == 0x0B:
        return "rated life exceeded — 0% remaining"
    return "unknown"


def _life_time_block(raw: str) -> "dict | None":
    raw = (raw or "").strip()
    if not raw:
        return None
    parts = raw.split()
    codes: list[int | None] = []
    for part in parts:
        try:
            codes.append(int(part, 16) if part.lower().startswith("0x") else int(part))
        except ValueError:
            codes.append(None)
    if not codes:
        return None
    if len(set(codes)) == 1:
        note = _life_time_note(codes[0])
    else:
        note = " / ".join(_life_time_note(code) for code in codes)
    return {"code": raw, "note": note}


def _eol_block(raw: str) -> "dict | None":
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        code = int(raw, 16) if raw.lower().startswith("0x") else int(raw)
    except ValueError:
        return {"code": raw, "note": "unknown"}
    return {"code": raw, "note": _EOL_REMARKS.get(code, "unknown")}


def _read_node_values(
    fields: list[tuple[str, str]],
    use_root: bool,
) -> dict[str, str]:
    """Read several sysfs nodes in one shell command."""
    if not fields:
        return {}
    command = "; ".join(
        f"printf '%s=' {shlex.quote(key)}; cat {shlex.quote(path)} 2>/dev/null; echo"
        for key, path in fields
    )
    if use_root:
        stdout, _, _ = su_shell(command, timeout=15)
    else:
        stdout, _, _ = shell(command, timeout=15)

    values: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if value:
            values[key] = value
    return values


def _read_ufs_health(use_root: bool) -> dict[str, str]:
    command = (
        "for d in /sys/class/scsi_device/*/device/health_descriptor "
        "/sys/bus/platform/drivers/ufshcd/*/health_descriptor; do "
        "if [ -d \"$d\" ]; then "
        "eol=$(cat \"$d/eol_info\" 2>/dev/null); "
        "[ -n \"$eol\" ] || eol=$(cat \"$d/pre_eol_info\" 2>/dev/null); "
        "printf 'eol=%s\\n' \"$eol\"; "
        "printf 'life_a='; cat \"$d/life_time_estimation_a\" 2>/dev/null; echo; "
        "printf 'life_b='; cat \"$d/life_time_estimation_b\" 2>/dev/null; echo; "
        "break; fi; done"
    )
    if use_root:
        stdout, _, _ = su_shell(command, timeout=15)
    else:
        stdout, _, _ = shell(command, timeout=15)
    values: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            value = value.strip()
            if value:
                values[key] = value
    return values


_HEALTH_FILE_NAMES = (
    "life_time",
    "pre_eol_info",
    "life_time_estimation_a",
    "life_time_estimation_b",
    "eol_info",
)


def _parse_nonroot_health(raw: str) -> dict[str, str]:
    """Parse readable sysfs health nodes and any labelled storaged fields."""
    values: dict[str, str] = {}
    current = ""
    in_sysfs = False
    for line in raw.splitlines():
        if line == "===STORAGED===":
            in_sysfs = False
            continue
        if line == "===SYSFS===":
            in_sysfs = True
            continue
        if line.startswith("===PATH:") and line.endswith("==="):
            path = line[8:-3]
            current = path.rsplit("/", 1)[-1]
            continue
        if current:
            value = line.strip()
            if value and current in _HEALTH_FILE_NAMES:
                values[current] = value
            current = ""
            continue
        if not in_sysfs:
            match = re.search(
                r"\b(life_time_estimation_[ab]|pre_eol_info|life_time|eol_info)"
                r"\b\s*[:=]\s*(.+)$",
                line,
                re.IGNORECASE,
            )
            if match:
                values[match.group(1).lower()] = match.group(2).strip()
    return values


def _read_nonroot_health(disk: str, kind: str) -> dict[str, str]:
    """Best-effort health read as the shell user.

    Some devices expose the eMMC/UFS health nodes world-readable.  Others do
    not, and there is no reliable non-root API for these counters.  This scans
    the paths the kernel normally uses and also asks storaged for any labelled
    health fields it happens to expose.
    """
    direct: list[str] = []
    if disk:
        base = shlex.quote(f"/sys/block/{disk}/device")
        direct.extend([
            f"{base}/life_time",
            f"{base}/pre_eol_info",
        ])
    direct.extend([
        "/sys/class/scsi_device/*/device/health_descriptor/eol_info",
        "/sys/class/scsi_device/*/device/health_descriptor/pre_eol_info",
        "/sys/class/scsi_device/*/device/health_descriptor/life_time_estimation_a",
        "/sys/class/scsi_device/*/device/health_descriptor/life_time_estimation_b",
        "/sys/bus/platform/drivers/ufshcd/*/health_descriptor/eol_info",
        "/sys/bus/platform/drivers/ufshcd/*/health_descriptor/pre_eol_info",
        "/sys/bus/platform/drivers/ufshcd/*/health_descriptor/life_time_estimation_a",
        "/sys/bus/platform/drivers/ufshcd/*/health_descriptor/life_time_estimation_b",
        "/sys/devices/platform/*/mmc_host/mmc*/mmc*:*/life_time",
        "/sys/devices/platform/*/mmc_host/mmc*/mmc*:*/pre_eol_info",
    ])
    name_filter = " -o ".join(f"-name {name}" for name in _HEALTH_FILE_NAMES)
    command = (
        "echo '===STORAGED==='; dumpsys storaged 2>/dev/null; "
        "echo '===SYSFS==='; "
        "for f in " + " ".join(direct) + " "
        "$(find /sys -type f \\( " + name_filter + " \\) 2>/dev/null); do "
        "[ -r \"$f\" ] || continue; "
        "printf '===PATH:%s===\\n' \"$f\"; "
        "cat \"$f\" 2>/dev/null; "
        "done"
    )
    stdout, _, _ = shell(command, timeout=20)
    return _parse_nonroot_health(stdout)


def _format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f}{unit}" if unit != "B" else f"{int(size)}B"
        size /= 1024
    return f"{value}B"


def _df_stats(path: str) -> dict:
    quoted = shlex.quote(path)
    stdout, _, rc = shell(f"df -h {quoted}", timeout=15)
    if rc != 0:
        return {}
    for line in stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        size, used, avail, used_pct = parts[-5:-1]
        try:
            pct = int(used_pct.rstrip("%"))
        except ValueError:
            pct = None
        return {
            "total": size,
            "used": used,
            "free": avail,
            "used_pct": pct,
        }
    return {}


def _parse_mount_dump(raw: str) -> tuple[dict[str, dict], dict[str, dict]]:
    """Parse the useful parts of ``dumpsys mount``."""
    disks: dict[str, dict] = {}
    volumes: dict[str, dict] = {}
    section = ""
    current: dict | None = None

    for line in raw.splitlines():
        stripped = line.strip()
        if stripped == "Disks:":
            section, current = "disks", None
            continue
        if stripped == "Volumes:":
            section, current = "volumes", None
            continue
        if stripped in ("Records:", "mObbMounts:"):
            section, current = "", None
            continue

        if section == "disks":
            m = re.match(r"DiskInfo\{disk:([^}]+)\}:", stripped)
            if m:
                current = {"id": m.group(1)}
                disks[current["id"]] = current
                continue
            if current is None:
                continue
            if "flags=" in stripped:
                current["flags"] = stripped.split("flags=", 1)[1].split()[0]
                size = re.search(r"\bsize=(\d+)", stripped)
                if size:
                    current["size_bytes"] = int(size.group(1))
                label = re.search(r"\blabel=(.*)$", stripped)
                if label:
                    current["label"] = label.group(1).strip()
            elif stripped.startswith("sysPath="):
                current["sys_path"] = stripped.split("=", 1)[1].strip()
            continue

        if section == "volumes":
            m = re.match(r"VolumeInfo\{([^}]+)\}:", stripped)
            if m:
                current = {"id": m.group(1)}
                volumes[current["id"]] = current
                continue
            if current is None:
                continue
            if stripped.startswith(("type=", "fsType=", "path=")):
                for key, value in re.findall(r"(\w+)=([^\s]*)", stripped):
                    current[key] = value

    return disks, volumes


def _parse_public_volumes(raw: str) -> list[dict]:
    volumes: list[dict] = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 3 or not parts[0].startswith("public:"):
            continue
        if parts[1] != "mounted":
            continue
        uuid = parts[2]
        if uuid in ("null", ""):
            continue
        volumes.append({"id": parts[0], "uuid": uuid})
    return volumes


def _internal_storage_kind(props: dict[str, str]) -> tuple[str, str]:
    disk = props.get("dev.mnt.rootdisk.data", "").strip()
    boot = props.get("ro.boot.boot_devices", "").lower()
    emmc = props.get("ro.boot.emmc", "").lower() == "true"

    if disk.startswith("mmcblk"):
        return "eMMC", disk
    if disk.startswith(("sd", "nvme")):
        return "UFS", disk
    if emmc or "sdhci" in boot:
        return "eMMC", disk
    if "ufs" in boot:
        return "UFS", disk
    return "Internal storage", disk


def _health_blocks(
    values: dict[str, str],
    kind: str,
) -> tuple[dict | None, dict | None]:
    """Build the UI health/EOL blocks from whatever values were readable."""
    ufs_life = (
        f"{values.get('life_time_estimation_a', '')} "
        f"{values.get('life_time_estimation_b', '')}"
    ).strip()
    if kind == "UFS":
        life_raw = ufs_life or values.get("life_time", "")
        eol_raw = values.get("eol_info") or values.get("pre_eol_info", "")
    else:
        life_raw = values.get("life_time", "") or ufs_life
        eol_raw = values.get("pre_eol_info") or values.get("eol_info", "")
    return _life_time_block(life_raw), _eol_block(eol_raw)


def _internal_health(disk: str, kind: str, root_available: bool) -> tuple[dict | None, dict | None, dict[str, str]]:
    values: dict[str, str] = {}
    if disk:
        base = f"/sys/block/{disk}/device"
        node_fields = [
            ("type", f"{base}/type"),
            ("name", f"{base}/name"),
            ("model", f"{base}/model"),
            ("date", f"{base}/date"),
            ("fwrev", f"{base}/fwrev"),
        ]
        if kind != "UFS":
            node_fields += [
                ("life_time", f"{base}/life_time"),
                ("pre_eol_info", f"{base}/pre_eol_info"),
            ]
        values.update(_read_node_values(node_fields, root_available))

    if kind == "UFS":
        ufs_values = _read_ufs_health(root_available)
        values.update({
            "eol_info": ufs_values.get("eol", ""),
            "life_time_estimation_a": ufs_values.get("life_a", ""),
            "life_time_estimation_b": ufs_values.get("life_b", ""),
            **{f"ufs_{key}": value for key, value in ufs_values.items()},
        })

    health, eol = _health_blocks(values, kind)

    # On a non-rooted device, the direct sysfs reads above usually fail.
    # Try the best-effort scan before declaring that root is required.
    if not root_available and (health is None or eol is None):
        fallback = _read_nonroot_health(disk, kind)
        if fallback:
            values.update(fallback)
            health, eol = _health_blocks(values, kind)

    return health, eol, values


def _split_sections(raw: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current = ""
    buffer: list[str] = []
    for line in raw.splitlines():
        if line.startswith("===") and line.endswith("==="):
            if current:
                sections[current] = "\n".join(buffer)
            current = line.strip("=").strip()
            buffer = []
        else:
            buffer.append(line)
    if current:
        sections[current] = "\n".join(buffer)
    return sections


def _parse_df_sections(raw: str) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for line in raw.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6:
            continue
        size, used, avail, used_pct = parts[-5:-1]
        mount = parts[-1]
        try:
            pct = int(used_pct.rstrip("%"))
        except ValueError:
            pct = None
        stats[mount] = {
            "total": size,
            "used": used,
            "free": avail,
            "used_pct": pct,
        }
    return stats


def storage_info(
    root_available: bool = False,
    props: "dict[str, str] | None" = None,
    volume_raw: "str | None" = None,
    mount_raw: "str | None" = None,
    df_stats: "dict[str, dict] | None" = None,
) -> dict:
    """Return internal and removable storage details exposed by Android."""
    props = props if props is not None else _getprop_map()
    kind, disk = _internal_storage_kind(props)

    if volume_raw is None:
        volume_raw, _, _ = shell("sm list-volumes all", timeout=15)
    if mount_raw is None:
        mount_raw, _, _ = shell("dumpsys mount", timeout=20)
    if not volume_raw and not mount_raw:
        return {"available": False, "error": "Storage information is not available."}

    disks, volumes = _parse_mount_dump(mount_raw)
    public_volumes = _parse_public_volumes(volume_raw)

    if df_stats is None:
        df_stats = {}
        internal_stats = _df_stats("/storage/emulated/0")
        if not internal_stats:
            internal_stats = _df_stats("/data")
    else:
        internal_stats = (
            df_stats.get("/storage/emulated")
            or df_stats.get("/storage/emulated/0")
            or df_stats.get("/data")
            or {}
        )

    health, eol, health_values = _internal_health(disk, kind, root_available)
    internal = {
        "kind": kind,
        "disk": disk,
        "name": health_values.get("name") or health_values.get("model") or "",
        "date": health_values.get("date", ""),
        "type_code": health_values.get("type", ""),
        "health": health,
        "eol": eol,
        "health_requires_root": bool(disk and not root_available and not health),
        "eol_requires_root": bool(disk and not root_available and not eol),
        **internal_stats,
    }

    external: list[dict] = []
    for pub in public_volumes:
        meta = volumes.get(pub["id"], {})
        uuid = pub["uuid"]
        mount_path = meta.get("path") or f"/storage/{uuid}"
        if mount_path == "null":
            mount_path = f"/storage/{uuid}"
        disk_id = meta.get("diskId", "").removeprefix("disk:")
        disk_meta = disks.get(disk_id, {})
        flags = disk_meta.get("flags", "")
        if "SD" in flags:
            removable_kind = "microSD"
        elif "USB" in flags:
            removable_kind = "USB storage"
        else:
            removable_kind = "Removable storage"

        stats = df_stats.get(mount_path) if df_stats else None
        if not stats and df_stats is not None:
            stats = _df_stats(mount_path)
        if not stats and disk_meta.get("size_bytes"):
            stats = {"total": _format_bytes(disk_meta["size_bytes"])}

        label = disk_meta.get("label") or meta.get("fsLabel") or ""
        label = "" if label.strip().lower() == "null" else label.strip()
        fs_type = meta.get("fsType", "")
        fs_type = "" if fs_type.strip().lower() == "null" else fs_type.strip()
        external.append({
            "kind": removable_kind,
            "label": label,
            "uuid": uuid,
            "fs_type": fs_type,
            "mount": mount_path,
            "health": None,
            "eol": None,
            **stats,
        })

    return {
        "available": True,
        "internal": internal,
        "external": external,
        "error": "",
    }


def system_report(root_available: "bool | None" = None) -> tuple[dict, dict, dict]:
    """Collect the Device tab payload with as few ADB round-trips as possible."""
    if root_available is None:
        root_available = has_root()

    prop_names = list(dict.fromkeys(_DEVICE_INFO_PROPS.values())) + [
        "ro.boot.emmc",
        "ro.boot.boot_devices",
        "ro.boot.ufs",
        "dev.mnt.rootdisk.data",
    ]
    prop_script = "; ".join(
        f"printf '%s=' {shlex.quote(name)}; getprop {shlex.quote(name)}"
        for name in prop_names
    )
    command = (
        "echo '===PROPS==='; "
        f"{prop_script}; "
        "echo '===BATTERY==='; dumpsys battery; "
        "echo '===VOLUMES==='; sm list-volumes all; "
        "echo '===MOUNT==='; dumpsys mount; "
        "echo '===DF_INTERNAL==='; df -h /storage/emulated/0; "
        "echo '===DF_EXTERNAL==='; df -h /storage/* 2>/dev/null"
    )
    raw, stderr, rc = shell(command, timeout=40)
    if rc != 0 and not raw:
        error = stderr or "Device details could not be read."
        return {}, {"available": False, "error": error}, {
            "available": False,
            "error": error,
        }

    sections = _split_sections(raw)
    props: dict[str, str] = {}
    for line in sections.get("PROPS", "").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            props[key.strip()] = value.strip()

    info = device_info(props)
    info["root"] = "Yes ✓" if root_available else "No — root actions unavailable"
    battery = battery_info(sections.get("BATTERY", ""))
    storage = storage_info(
        root_available=root_available,
        props=props,
        volume_raw=sections.get("VOLUMES", ""),
        mount_raw=sections.get("MOUNT", ""),
        df_stats=_parse_df_sections(sections.get("DF_EXTERNAL", "")),
    )
    return info, battery, storage


def has_root() -> bool:
    variant = _get_su_variant()
    if variant is None:
        return False
    stdout, _, rc = shell(variant.format(cmd=shlex.quote("id")))
    return rc == 0 and "uid=0" in stdout


def list_dir(path: str) -> list[dict]:
    quoted = shlex.quote(path)
    stdout, stderr, rc = su_shell(f"ls -la {quoted}")
    if rc != 0:
        stdout, stderr, rc = shell(f"ls -la {quoted}")
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
    cmd = f"rm -rf {shlex.quote(path)}"
    if use_root:
        stdout, stderr, rc = su_shell(cmd)
        if rc == 0:
            return True, stdout or stderr
        # Root unavailable or failed — still try as the normal shell user
        # so that user-owned files (e.g. /sdcard) can be deleted.
    stdout, stderr, rc = shell(cmd)
    return rc == 0, stdout or stderr
