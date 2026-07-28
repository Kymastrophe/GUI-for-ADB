from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QGridLayout, QTextEdit, QFileDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject

from core import adb


class InfoLoader(QObject):
    done = pyqtSignal(dict, str, str)

    def run(self):
        try:
            info = adb.device_info()
            info["root"] = "Yes ✓" if adb.has_root() else "No — root actions unavailable"
            bat_out, _, _  = adb.shell("dumpsys battery")
            stor_out, _, _ = adb.shell("df -h /sdcard /data 2>/dev/null || df -h")
            self.done.emit(info, bat_out, stor_out)
        except Exception as e:
            self.done.emit({}, "", str(e))


class DeviceTab(QWidget):
    log_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._info_thread: QThread     | None = None
        self._info_worker: InfoLoader  | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        info_box = QGroupBox("Device Information")
        grid = QGridLayout(info_box)
        self._info_labels: dict[str, QLabel] = {}
        fields = [
            ("brand",   "Brand"),
            ("model",   "Model"),
            ("android", "Android"),
            ("sdk",     "SDK Level"),
            ("serial",  "Serial"),
            ("build",   "Build ID"),
            ("root",    "Root Access"),
        ]
        for row, (key, label) in enumerate(fields):
            grid.addWidget(QLabel(f"{label}:"), row, 0)
            val = QLabel("—")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._info_labels[key] = val
            grid.addWidget(val, row, 1)
        root.addWidget(info_box)

        bat_box = QGroupBox("Battery / Storage")
        bat_l = QVBoxLayout(bat_box)
        self._bat_text = QTextEdit()
        self._bat_text.setReadOnly(True)
        self._bat_text.setMaximumHeight(100)
        bat_l.addWidget(self._bat_text)
        self._stor_text = QTextEdit()
        self._stor_text.setReadOnly(True)
        self._stor_text.setMaximumHeight(100)
        bat_l.addWidget(self._stor_text)
        root.addWidget(bat_box)

        ctrl_box = QGroupBox("Controls")
        ctrl_l = QHBoxLayout(ctrl_box)

        self._refresh_btn = QPushButton("↻  Refresh Info")
        self._refresh_btn.clicked.connect(self.refresh)
        ctrl_l.addWidget(self._refresh_btn)

        for label, mode in [("Reboot", ""), ("→ Recovery", "recovery"), ("→ Bootloader", "bootloader")]:
            btn = QPushButton(label)
            btn.clicked.connect(self._make_reboot_handler(mode))
            ctrl_l.addWidget(btn)

        screenshot_btn = QPushButton("📷  Screenshot")
        screenshot_btn.clicked.connect(self._screenshot)
        ctrl_l.addWidget(screenshot_btn)

        ctrl_l.addStretch()
        root.addWidget(ctrl_box)

        self._status = QLabel("")
        root.addWidget(self._status)
        root.addStretch()

    def _make_reboot_handler(self, mode: str):
        def handler():
            ok, msg = adb.reboot(mode)
            self.log_message.emit(f"Reboot {mode or 'system'}: {msg}")
            self._status.setText(msg)
        return handler

    def refresh(self):
        if not adb.is_connected():
            self._status.setText("No device connected.")
            return
        if self._info_thread and self._info_thread.isRunning():
            return

        self._refresh_btn.setEnabled(False)
        self._status.setText("Loading…")

        self._info_worker = InfoLoader()
        self._info_thread = QThread()
        self._info_worker.moveToThread(self._info_thread)
        self._info_worker.done.connect(self._on_loaded)
        self._info_worker.done.connect(self._info_thread.quit)
        self._info_thread.started.connect(self._info_worker.run)
        self._info_thread.finished.connect(lambda: self._refresh_btn.setEnabled(True))
        self._info_thread.start()

    def _on_loaded(self, info: dict, bat: str, stor: str):
        for key, lbl in self._info_labels.items():
            lbl.setText(info.get(key, "—") or "—")
        self._bat_text.setPlainText(bat.strip())
        self._stor_text.setPlainText(stor.strip())
        self._status.setText("Loaded.")

    def _screenshot(self):
        dest, _ = QFileDialog.getSaveFileName(
            self, "Save Screenshot", "screenshot.png", "PNG (*.png)"
        )
        if not dest:
            return
        _, _, rc = adb.shell("screencap -p /sdcard/_adb_screenshot.png")
        if rc != 0:
            self._status.setText("screencap failed.")
            return
        ok, msg = adb.pull_file("/sdcard/_adb_screenshot.png", dest)
        adb.shell("rm /sdcard/_adb_screenshot.png")
        self._status.setText(msg)
        self.log_message.emit(f"Screenshot: {msg}")

    def showEvent(self, event):
        super().showEvent(event)
        if adb.is_connected():
            self.refresh()
