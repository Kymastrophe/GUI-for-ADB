import sys
import socket
import random
import string
import subprocess
import time
from typing import Optional

try:
    import qrcode
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False


def _random_psk(length: int = 12) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.137.1"


def wifi_qr_string(ssid: str, psk: str, hidden: bool = False) -> str:
    def esc(s):
        for c in ['\\', ';', ',', '"', ':']:
            s = s.replace(c, '\\' + c)
        return s
    h = "true" if hidden else "false"
    return f"WIFI:T:WPA;S:{esc(ssid)};P:{esc(psk)};H:{h};;"


def _make_qr_pixmap(data: str, box_size: int = 8):
    if not HAS_QRCODE:
        return None
    try:
        import io
        from PyQt6.QtGui import QPixmap, QImage
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return QPixmap.fromImage(QImage.fromData(buf.read()))
    except Exception:
        return None


class HotspotManager:
    def __init__(self):
        self.ssid: Optional[str] = None
        self.psk: Optional[str] = None
        self.host_ip: Optional[str] = None
        self._active = False

    def start(self, ssid: str = "ADB-Manager", psk: Optional[str] = None) -> tuple[bool, str]:
        self.ssid = ssid
        self.psk = psk or _random_psk()
        ok, msg = False, "Unsupported platform"

        if sys.platform.startswith("win"):
            ok, msg = self._start_windows()
        elif sys.platform.startswith("linux"):
            ok, msg = self._start_linux()
        elif sys.platform == "darwin":
            ok, msg = self._start_macos()

        if ok:
            self._active = True
            time.sleep(2)
            self.host_ip = _get_local_ip()
        return ok, msg

    def stop(self):
        if not self._active:
            return
        try:
            if sys.platform.startswith("win"):
                subprocess.run(
                    ["netsh", "wlan", "stop", "hostednetwork"],
                    capture_output=True
                )
            elif sys.platform.startswith("linux"):
                subprocess.run(
                    ["nmcli", "connection", "down", self.ssid or "ADB-Manager"],
                    capture_output=True
                )
        except Exception:
            pass
        self._active = False

    def _start_windows(self) -> tuple[bool, str]:
        for cmd in [
            ["netsh", "wlan", "set", "hostednetwork", "mode=allow",
             f"ssid={self.ssid}", f"key={self.psk}"],
            ["netsh", "wlan", "start", "hostednetwork"],
        ]:
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                return False, r.stderr or r.stdout
        return True, "Hotspot started (Windows)"

    def _start_linux(self) -> tuple[bool, str]:
        if subprocess.run(["which", "nmcli"], capture_output=True).returncode != 0:
            return False, "nmcli not found. Install NetworkManager."
        name = self.ssid or "ADB-Manager"
        subprocess.run(["nmcli", "connection", "delete", name], capture_output=True)
        r = subprocess.run([
            "nmcli", "connection", "add",
            "type", "wifi", "ifname", "*", "con-name", name,
            "autoconnect", "yes", "ssid", name,
            "mode", "ap", "ipv4.method", "shared",
            "wifi-sec.key-mgmt", "wpa-psk",
            "wifi-sec.psk", self.psk,
        ], capture_output=True, text=True)
        if r.returncode != 0:
            return False, r.stderr
        r2 = subprocess.run(
            ["nmcli", "connection", "up", name],
            capture_output=True, text=True
        )
        return r2.returncode == 0, r2.stdout or r2.stderr

    def _start_macos(self) -> tuple[bool, str]:
        return False, (
            "macOS does not support programmatic hotspot creation.\n"
            "Enable Internet Sharing manually:\n"
            "System Settings → General → Sharing → Internet Sharing\n"
            "Then use the Manual Connection panel."
        )
