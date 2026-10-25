import sys
import re
import socket
import subprocess
import ipaddress
import concurrent.futures
import threading
import time
from typing import Callable, Optional

from core.adb import run as adb_run


def mdns_find(timeout: int = 8, stop_event: Optional[threading.Event] = None) -> list[dict]:
    results = []
    deadline = time.time() + timeout
    seen = set()
    while time.time() < deadline:
        if stop_event is not None and stop_event.is_set():
            break
        try:
            stdout, _, rc = adb_run(["mdns", "services"], timeout=4)
            for line in stdout.splitlines():
                m = re.search(r'_adb-tls-connect\._tcp\s+(\d+\.\d+\.\d+\.\d+):(\d+)', line)
                if m:
                    ip, port = m.group(1), int(m.group(2))
                    key = f"{ip}:{port}"
                    if key not in seen:
                        seen.add(key)
                        results.append({"ip": ip, "port": port, "serial": key})
        except Exception:
            pass
        if results:
            break
        time.sleep(1)
    return results


def _our_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.137.1"


def _read_arp() -> list[str]:
    ips = []
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/net/arp") as f:
                for line in f.readlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 3 and parts[2] == "0x2":
                        ips.append(parts[0])
            if ips:
                return ips
        except Exception:
            pass
    try:
        r = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=5)
        found = re.findall(r"(\d+\.\d+\.\d+\.\d+)", r.stdout)
        ips.extend(found)
    except Exception:
        pass
    return list(set(ips))


def _ping_sweep(subnet_ip: str, workers: int = 60,
                stop_event: Optional[threading.Event] = None) -> None:
    try:
        net = ipaddress.IPv4Network(subnet_ip + "/24", strict=False)
        hosts = [str(h) for h in net.hosts() if str(h) != subnet_ip]
    except Exception:
        return

    def _ping(ip):
        if stop_event is not None and stop_event.is_set():
            return
        try:
            if sys.platform.startswith("win"):
                subprocess.run(
                    ["ping", "-n", "1", "-w", "300", ip],
                    capture_output=True, timeout=2
                )
            else:
                subprocess.run(
                    ["ping", "-c", "1", "-W", "1", ip],
                    capture_output=True, timeout=2
                )
        except Exception:
            pass

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        ex.map(_ping, hosts)


def _try_adb_connect(ip: str, port: int = 5555, timeout: int = 3) -> Optional[str]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((ip, port))
    except Exception:
        return None

    stdout, stderr, rc = adb_run(["connect", f"{ip}:{port}"], timeout=6)
    combined = (stdout + stderr).lower()
    if "connected" in combined and "unable" not in combined:
        return f"{ip}:{port}"
    return None


def arp_find(our_ip: str, connect_port: int = 5555, timeout: int = 15,
             stop_event: Optional[threading.Event] = None) -> list[dict]:
    sweep_thread = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    sweep_thread.submit(_ping_sweep, our_ip, 60, stop_event)

    deadline = time.time() + timeout
    found = []
    seen_ips = {our_ip}

    while time.time() < deadline:
        if stop_event is not None and stop_event.is_set():
            break
        arp_ips = _read_arp()
        new_ips = [ip for ip in arp_ips if ip not in seen_ips]

        if new_ips:
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
                results = list(ex.map(lambda ip: _try_adb_connect(ip, connect_port), new_ips))
            for ip, serial in zip(new_ips, results, strict=True):
                seen_ips.add(ip)
                if serial:
                    found.append({"ip": ip, "port": connect_port, "serial": serial})

        if found:
            break
        time.sleep(1.5)

    sweep_thread.shutdown(wait=False)
    return found


def find_phone(
    our_ip: Optional[str] = None,
    connect_port: int = 5555,
    timeout: int = 30,
    on_status: Optional[Callable[[str], None]] = None,
    stop_event: Optional[threading.Event] = None,
) -> Optional[dict]:
    def emit(msg):
        if on_status:
            on_status(msg)

    our_ip = our_ip or _our_ip()
    emit(f"Searching for phone on {our_ip.rsplit('.', 1)[0]}.0/24 …")

    result_holder = []
    done = threading.Event()

    def try_mdns():
        emit("Checking mDNS (adb mdns services)…")
        hits = mdns_find(timeout=min(timeout, 10), stop_event=stop_event)
        if hits and not done.is_set():
            done.set()
            result_holder.append(hits[0])

    def try_arp():
        time.sleep(1)
        if stop_event is not None and stop_event.is_set():
            return
        emit("Scanning subnet via ARP…")
        hits = arp_find(our_ip, connect_port=connect_port, timeout=max(timeout - 2, 1),
                        stop_event=stop_event)
        if hits and not done.is_set():
            done.set()
            result_holder.append(hits[0])

    threads = [
        threading.Thread(target=try_mdns, daemon=True),
        threading.Thread(target=try_arp, daemon=True),
    ]
    for t in threads:
        t.start()

    deadline = time.time() + timeout
    while time.time() < deadline:
        if done.wait(0.2):
            break
        if stop_event is not None and stop_event.is_set():
            break
    return result_holder[0] if result_holder else None
