import threading

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QGroupBox, QTextEdit, QSizePolicy, QSpinBox,
    QFrame, QScrollArea,
)
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, QObject

from core import adb
from core.hotspot_qr import HotspotManager, wifi_qr_string, _make_qr_pixmap, _get_local_ip
from core.phone_finder import find_phone


class HotspotWorker(QObject):
    status   = pyqtSignal(str)
    wifi_qr  = pyqtSignal(object, str)
    finished = pyqtSignal(str)

    def __init__(self, ssid: str, psk: str):
        super().__init__()
        self.ssid = ssid
        self.psk  = psk
        self._mgr = HotspotManager()

    def run(self):
        self.status.emit("Creating hotspot…")
        ok, msg = self._mgr.start(ssid=self.ssid, psk=self.psk or None)
        actual_psk = self._mgr.psk
        host_ip    = self._mgr.host_ip or _get_local_ip()

        if not ok:
            self.status.emit(f"Hotspot failed: {msg}")
            self.status.emit("Continuing — ensure phone is on same Wi-Fi.")
        else:
            self.status.emit(f"Hotspot ready  •  SSID: {self.ssid}  •  Host: {host_ip}")

        wifi_str = wifi_qr_string(self.ssid, actual_psk)
        self.wifi_qr.emit(_make_qr_pixmap(wifi_str), wifi_str)
        self.finished.emit(host_ip)

    def stop(self):
        self._mgr.stop()


class FindPhoneWorker(QObject):
    status = pyqtSignal(str)
    found  = pyqtSignal(str, int)
    failed = pyqtSignal(str)

    def __init__(self, our_ip: str, port: int):
        super().__init__()
        self.our_ip = our_ip
        self.port   = port
        self._stop  = threading.Event()

    def run(self):
        result = find_phone(
            our_ip=self.our_ip,
            connect_port=self.port,
            timeout=30,
            on_status=lambda m: self.status.emit(m),
            stop_event=self._stop,
        )
        if self._stop.is_set():
            return
        if result:
            self.found.emit(result["ip"], result["port"])
        else:
            self.failed.emit(
                "Phone not found automatically.\n"
                "Enter IP and port from Wireless Debugging settings manually."
            )

    def stop(self):
        self._stop.set()


class ConnectTab(QWidget):
    device_connected    = pyqtSignal(str)
    device_disconnected = pyqtSignal(str)
    _devices_polled     = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._host_ip = ""
        self._hotspot_worker: HotspotWorker   | None = None
        self._hotspot_thread: QThread         | None = None
        self._find_worker:    FindPhoneWorker | None = None
        self._find_thread:    QThread         | None = None
        self._connected_serials: set[str] = set()
        self._last_device_state: tuple[tuple[str, str], ...] | None = None
        self._poll_in_flight = False
        self._polling_stopped = False
        self._build_ui()

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(2000)
        self._poll_timer.timeout.connect(self._poll_devices)
        self._devices_polled.connect(self._on_devices_polled)
        self._poll_timer.start()
        self._poll_devices()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        self._status_label = QLabel("No device connected.")
        self._status_label.setObjectName("statusLabel")
        self._status_label.setProperty("tone", "muted")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._status_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        cols = QHBoxLayout()
        root.addLayout(cols)

        left = QGroupBox("Wireless Pairing Wizard")
        ll = QVBoxLayout(left)

        s1 = QLabel("Step 1 — Create hotspot & get phone on same network")
        s1.setObjectName("sectionLabel")
        ll.addWidget(s1)

        net_row = QHBoxLayout()
        net_row.addWidget(QLabel("SSID:"))
        self._ssid_edit = QLineEdit("ADB-Manager")
        net_row.addWidget(self._ssid_edit)
        net_row.addWidget(QLabel("Password:"))
        self._psk_edit = QLineEdit()
        self._psk_edit.setPlaceholderText("auto-generated")
        net_row.addWidget(self._psk_edit)
        ll.addLayout(net_row)

        hs_row = QHBoxLayout()
        self._hotspot_btn = QPushButton("▶  Create Hotspot & Show QR")
        self._hotspot_btn.clicked.connect(self._start_hotspot)
        hs_row.addWidget(self._hotspot_btn)
        self._hotspot_stop_btn = QPushButton("■  Stop Hotspot")
        self._hotspot_stop_btn.setEnabled(False)
        self._hotspot_stop_btn.clicked.connect(self._stop_hotspot)
        hs_row.addWidget(self._hotspot_stop_btn)
        ll.addLayout(hs_row)

        self._wifi_qr_label = QLabel("Wi-Fi QR will appear here\nScan with phone camera to join hotspot")
        self._wifi_qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._wifi_qr_label.setMinimumSize(200, 200)
        self._wifi_qr_label.setMaximumHeight(260)
        self._wifi_qr_label.setFrameShape(QFrame.Shape.Box)
        self._wifi_qr_label.setObjectName("qrPlaceholder")
        self._wifi_qr_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._wifi_qr_label.setWordWrap(True)
        ll.addWidget(self._wifi_qr_label)

        s2 = QLabel("Step 2 — Enable Wireless Debugging, then find the phone")
        s2.setObjectName("sectionLabel")
        ll.addWidget(s2)

        instr = QLabel(
            "Settings → Developer options → Wireless debugging → Enable\n"
            "Then click Find & Connect."
        )
        instr.setObjectName("hintLabel")
        ll.addWidget(instr)

        find_row = QHBoxLayout()
        self._find_btn = QPushButton("🔍  Find Phone & Connect")
        self._find_btn.setEnabled(False)
        self._find_btn.clicked.connect(self._find_and_connect)
        find_row.addWidget(self._find_btn)
        self._find_stop_btn = QPushButton("■")
        self._find_stop_btn.setMaximumWidth(32)
        self._find_stop_btn.setEnabled(False)
        self._find_stop_btn.clicked.connect(self._stop_find)
        find_row.addWidget(self._find_stop_btn)
        ll.addLayout(find_row)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(90)
        self._log.document().setMaximumBlockCount(500)
        ll.addWidget(self._log)

        cols.addWidget(left, stretch=3)

        right = QGroupBox("Manual Connection")
        rl = QVBoxLayout(right)

        rl.addWidget(QLabel("Phone IP (from Wireless Debugging screen):"))
        self._host_edit = QLineEdit()
        self._host_edit.setPlaceholderText("192.168.x.x  (auto-filled on find)")
        rl.addWidget(self._host_edit)

        rl.addWidget(QLabel("Port:"))
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1024, 65535)
        self._port_spin.setValue(5555)
        rl.addWidget(self._port_spin)

        connect_btn = QPushButton("⚡  Connect")
        connect_btn.clicked.connect(self._manual_connect)
        rl.addWidget(connect_btn)

        rl.addWidget(QLabel(" "))
        rl.addWidget(QLabel("Pair first (Android 11+):"))
        rl.addWidget(QLabel("Pair port:"))
        self._pair_port_spin = QSpinBox()
        self._pair_port_spin.setRange(1024, 65535)
        self._pair_port_spin.setValue(37000)
        rl.addWidget(self._pair_port_spin)

        rl.addWidget(QLabel("Pair code:"))
        self._pair_code_edit = QLineEdit()
        self._pair_code_edit.setPlaceholderText("6-digit code shown on phone")
        rl.addWidget(self._pair_code_edit)

        pair_btn = QPushButton("Pair")
        pair_btn.clicked.connect(self._manual_pair)
        rl.addWidget(pair_btn)

        rl.addStretch()

        rl.addWidget(QLabel("Connected devices:"))
        self._devices_list = QTextEdit()
        self._devices_list.setReadOnly(True)
        self._devices_list.setMaximumHeight(110)
        rl.addWidget(self._devices_list)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("↻  Refresh")
        refresh_btn.setToolTip("Devices are also detected automatically every 2 seconds.")
        refresh_btn.clicked.connect(self._refresh_devices)
        btn_row.addWidget(refresh_btn)
        disconnect_btn = QPushButton("Disconnect All")
        disconnect_btn.clicked.connect(self._disconnect_all)
        btn_row.addWidget(disconnect_btn)
        rl.addLayout(btn_row)

        cols.addWidget(right, stretch=2)

        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

    def _start_hotspot(self):
        if self._hotspot_thread and self._hotspot_thread.isRunning():
            return
        self._hotspot_btn.setEnabled(False)
        self._hotspot_stop_btn.setEnabled(True)
        self._log.clear()
        self._wifi_qr_label.clear()
        self._wifi_qr_label.setText("Creating hotspot…")

        self._hotspot_worker = HotspotWorker(
            ssid=self._ssid_edit.text().strip() or "ADB-Manager",
            psk=self._psk_edit.text().strip(),
        )
        self._hotspot_thread = QThread()
        self._hotspot_worker.moveToThread(self._hotspot_thread)
        self._hotspot_worker.status.connect(self._log_msg)
        self._hotspot_worker.wifi_qr.connect(self._on_wifi_qr)
        self._hotspot_worker.finished.connect(self._on_hotspot_done)
        self._hotspot_worker.finished.connect(self._hotspot_thread.quit)
        self._hotspot_thread.started.connect(self._hotspot_worker.run)
        self._hotspot_thread.start()

    def _stop_hotspot(self):
        if self._hotspot_worker:
            self._hotspot_worker.stop()
        self._hotspot_btn.setEnabled(True)
        self._hotspot_stop_btn.setEnabled(False)
        self._find_btn.setEnabled(False)
        self._log_msg("Hotspot stopped.")

    def _on_wifi_qr(self, pixmap, qr_string: str):
        if pixmap:
            scaled = pixmap.scaled(
                max(self._wifi_qr_label.width() - 8, 200),
                max(self._wifi_qr_label.height() - 8, 200),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._wifi_qr_label.setPixmap(scaled)
        else:
            self._wifi_qr_label.setText(
                "qrcode / Pillow not installed.\n"
                f"Connect manually to:\n{qr_string}"
            )

    def _on_hotspot_done(self, host_ip: str):
        self._host_ip = host_ip
        self._hotspot_btn.setEnabled(True)
        self._find_btn.setEnabled(True)

    def _find_and_connect(self):
        if self._find_thread and self._find_thread.isRunning():
            return
        self._find_btn.setEnabled(False)
        self._find_stop_btn.setEnabled(True)
        self._log_msg("Searching for phone…")

        self._find_worker = FindPhoneWorker(
            our_ip=self._host_ip or _get_local_ip(),
            port=self._port_spin.value(),
        )
        self._find_thread = QThread()
        self._find_worker.moveToThread(self._find_thread)
        self._find_worker.status.connect(self._log_msg)
        self._find_worker.found.connect(self._on_phone_found)
        self._find_worker.failed.connect(self._on_phone_not_found)
        self._find_worker.found.connect(self._find_thread.quit)
        self._find_worker.failed.connect(self._find_thread.quit)
        self._find_thread.finished.connect(self._on_find_done)
        self._find_thread.started.connect(self._find_worker.run)
        self._find_thread.start()

    def _stop_find(self):
        self._find_stop_btn.setEnabled(False)
        if self._find_worker:
            self._find_worker.stop()
        if self._find_thread and self._find_thread.isRunning():
            self._find_thread.quit()

    def _set_status(self, msg: str, tone: str = "info"):
        self._status_label.setText(msg)
        if self._status_label.property("tone") != tone:
            self._status_label.setProperty("tone", tone)
            self._status_label.style().unpolish(self._status_label)
            self._status_label.style().polish(self._status_label)

    def _on_phone_found(self, ip: str, port: int):
        self._log_msg(f"Found {ip}:{port} — connecting…")
        self._host_edit.setText(ip)
        self._port_spin.setValue(port)
        ok, msg = adb.connect(ip, port)
        self._log_msg(msg, "success" if ok else "danger")
        if ok:
            self._refresh_devices()

    def _on_phone_not_found(self, msg: str):
        self._log_msg(msg, "danger")
        self._set_status("Phone not found — enter IP manually.", "danger")

    def _on_find_done(self):
        self._find_btn.setEnabled(True)
        self._find_stop_btn.setEnabled(False)

    def _manual_connect(self):
        host = self._host_edit.text().strip()
        if not host:
            self._set_status("Enter a phone IP address.", "danger")
            return
        ok, msg = adb.connect(host, self._port_spin.value())
        self._log_msg(msg, "success" if ok else "danger")
        if ok:
            self._refresh_devices()

    def _manual_pair(self):
        host = self._host_edit.text().strip()
        code = self._pair_code_edit.text().strip()
        if not host or not code:
            self._set_status("Enter phone IP and pair code.", "danger")
            return
        ok, msg = adb.pair(host, self._pair_port_spin.value(), code)
        self._log_msg(msg, "success" if ok else "danger")
        if ok:
            self._manual_connect()

    def _log_msg(self, msg: str, tone: str = "info"):
        self._log.append(msg)
        self._set_status(msg, tone)

    def _refresh_devices(self):
        # The poll runs off the UI thread so a slow/hung ADB server cannot
        # freeze the window while it is being detected.
        self._poll_devices()

    def _poll_devices(self):
        if self._polling_stopped or self._poll_in_flight:
            return
        self._poll_in_flight = True
        threading.Thread(
            target=self._poll_worker,
            name="adb-device-poll",
            daemon=True,
        ).start()

    def _poll_worker(self):
        try:
            devs = adb.devices(timeout=5)
        except Exception:
            devs = []
        if self._polling_stopped:
            return
        try:
            self._devices_polled.emit(devs)
        except RuntimeError:
            # The tab was destroyed while the background poll was running.
            pass

    def _on_devices_polled(self, devs: list[dict]):
        self._poll_in_flight = False
        if self._polling_stopped:
            return
        self._apply_devices(devs)

    def _apply_devices(self, devs: list[dict]):
        text = "\n".join(f"{d['serial']}  [{d['state']}]" for d in devs) or "(none)"
        if self._devices_list.toPlainText() != text:
            self._devices_list.setPlainText(text)

        connected = {d["serial"] for d in devs if d["state"] == "device"}
        added   = sorted(connected - self._connected_serials)
        removed = sorted(self._connected_serials - connected)
        self._connected_serials = connected

        for serial in removed:
            self._log.append(f"Device disconnected: {serial}")
            self.device_disconnected.emit(serial)
        for serial in added:
            self._log.append(f"Device detected: {serial}")
            self.device_connected.emit(serial)

        state = tuple(sorted((d["serial"], d["state"]) for d in devs))
        if state != self._last_device_state:
            self._last_device_state = state
            if connected:
                self._set_status(f"✓ {len(connected)} device(s) connected", "success")
            elif devs:
                self._set_status("No usable device — check authorization.", "danger")
            else:
                self._set_status("No device connected.", "muted")

    def _disconnect_all(self):
        self._set_status(adb.disconnect_all(), "info")
        self._refresh_devices()

    def stop_polling(self) -> None:
        self._polling_stopped = True
        self._poll_timer.stop()

    def closeEvent(self, event):
        self.stop_polling()
        super().closeEvent(event)
