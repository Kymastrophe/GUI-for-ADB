from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QGroupBox,
    QGridLayout, QFileDialog, QScrollArea, QFrame, QProgressBar,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont

from core import adb


_INFO_FIELDS = [
    ("brand",          "Brand"),
    ("model",          "Model"),
    ("device",         "Device"),
    ("board",          "Board"),
    ("android",        "Android"),
    ("sdk",            "SDK Level"),
    ("security_patch", "Security Patch"),
    ("abi",            "ABI"),
    ("serial",         "Serial"),
    ("build",          "Build ID"),
    ("build_type",     "Build Type"),
    ("root",           "Root Access"),
]

_BATTERY_FIELDS = [
    ("health",    "Health"),
    ("power",     "Power source"),
    ("voltage",   "Voltage"),
    ("temperature", "Temperature"),
    ("technology", "Technology"),
    ("charge",    "Charge counter"),
    ("capacity",  "Capacity"),
]


class InfoLoader(QObject):
    done = pyqtSignal(dict, dict, dict)

    def run(self):
        try:
            if not adb.is_connected():
                self.done.emit({}, {}, {"error": "No device connected."})
                return
            info, battery, storage = adb.system_report()
            self.done.emit(info, battery, storage)
        except Exception as e:
            self.done.emit({}, {}, {"error": str(e)})


class DeviceTab(QWidget):
    log_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._info_thread: QThread    | None = None
        self._info_worker: InfoLoader | None = None
        self._build_ui()

    # ── UI construction ─────────────────────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(self._build_info_box(), stretch=1)
        top.addWidget(self._build_battery_box(), stretch=1)
        top.addWidget(self._build_storage_box(), stretch=1)
        root.addLayout(top, stretch=1)

        self._status = QLabel("No device connected.")
        self._status.setObjectName("mutedLabel")
        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)
        # Keep the controls outside the scroll area so they remain reachable
        # even when the window is at its minimum height.
        outer.addWidget(self._build_controls_box(), stretch=0)
        outer.addWidget(self._status)

    def _build_info_box(self) -> QGroupBox:
        box = QGroupBox("Device Information")
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        grid = QGridLayout(box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(7)

        self._info_labels: dict[str, QLabel] = {}
        for row, (key, label) in enumerate(_INFO_FIELDS):
            name_lbl = QLabel(f"{label}:")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            grid.addWidget(name_lbl, row, 0)

            val = QLabel("—")
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            val.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self._info_labels[key] = val
            grid.addWidget(val, row, 1)

        grid.setRowStretch(len(_INFO_FIELDS), 1)
        return box

    def _build_battery_box(self) -> QGroupBox:
        box = QGroupBox("Battery")
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(10)
        self._bat_pct = QLabel("—")
        f = QFont()
        f.setBold(True)
        f.setPointSize(22)
        self._bat_pct.setFont(f)
        head.addWidget(self._bat_pct)

        self._bat_status = QLabel("")
        self._bat_status.setObjectName("mutedLabel")
        head.addWidget(self._bat_status, 1, Qt.AlignmentFlag.AlignBottom)
        lay.addLayout(head)

        self._bat_bar = QProgressBar()
        self._bat_bar.setRange(0, 100)
        self._bat_bar.setTextVisible(False)
        self._bat_bar.setFixedHeight(8)
        self._bat_bar.setToolTip("Battery level")
        lay.addWidget(self._bat_bar)

        grid = QGridLayout()
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self._bat_labels: dict[str, QLabel] = {}
        for row, (key, label) in enumerate(_BATTERY_FIELDS):
            name_lbl = QLabel(f"{label}:")
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            grid.addWidget(name_lbl, row, 0)

            val = QLabel("—")
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._bat_labels[key] = val
            grid.addWidget(val, row, 1)
        lay.addLayout(grid)
        lay.addStretch(1)
        return box

    def _build_storage_box(self) -> QGroupBox:
        box = QGroupBox("Storage")
        box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self._int_heading = QLabel("Internal storage")
        heading_font = QFont()
        heading_font.setBold(True)
        heading_font.setPointSize(10)
        self._int_heading.setFont(heading_font)
        lay.addWidget(self._int_heading)

        self._int_bar = QProgressBar()
        self._int_bar.setRange(0, 100)
        self._int_bar.setTextVisible(False)
        self._int_bar.setFixedHeight(8)
        lay.addWidget(self._int_bar)

        self._int_usage = QLabel("—")
        self._int_usage.setWordWrap(True)
        self._int_usage.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._int_usage)

        self._int_health = QLabel("Health: —")
        self._int_health.setWordWrap(True)
        self._int_health.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._int_health)

        self._int_eol = QLabel("Pre-EOL: —")
        self._int_eol.setWordWrap(True)
        self._int_eol.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._int_eol)

        self._int_meta = QLabel("")
        self._int_meta.setObjectName("mutedLabel")
        self._int_meta.setWordWrap(True)
        lay.addWidget(self._int_meta)

        self._ext_sep = QFrame()
        self._ext_sep.setFrameShape(QFrame.Shape.HLine)
        self._ext_sep.setFrameShadow(QFrame.Shadow.Sunken)
        self._ext_sep.setFixedHeight(1)
        self._ext_sep.setVisible(False)
        lay.addWidget(self._ext_sep)

        self._ext_container = QWidget()
        self._ext_layout = QVBoxLayout(self._ext_container)
        self._ext_layout.setContentsMargins(0, 0, 0, 0)
        self._ext_layout.setSpacing(8)
        self._ext_container.setVisible(False)
        lay.addWidget(self._ext_container)
        lay.addStretch(1)
        return box

    def _build_controls_box(self) -> QGroupBox:
        box = QGroupBox("Controls")
        ctrl_l = QHBoxLayout(box)
        ctrl_l.setContentsMargins(0, 0, 0, 0)

        self._refresh_btn = QPushButton("↻  Refresh Info")
        self._refresh_btn.clicked.connect(self.refresh)
        ctrl_l.addWidget(self._refresh_btn)

        for label, mode in [
            ("Reboot", ""),
            ("→ Recovery", "recovery"),
            ("→ Bootloader", "bootloader"),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(self._make_reboot_handler(mode))
            ctrl_l.addWidget(btn)

        screenshot_btn = QPushButton("📷  Screenshot")
        screenshot_btn.clicked.connect(self._screenshot)
        ctrl_l.addWidget(screenshot_btn)

        ctrl_l.addStretch()
        return box

    # ── Data loading ────────────────────────────────────────────────────────
    def refresh(self):
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
        self._info_thread.finished.connect(self._on_thread_done)
        self._info_thread.start()

    def _on_thread_done(self):
        self._refresh_btn.setEnabled(True)

    def _on_loaded(self, info: dict, battery: dict, storage: dict):
        if not info:
            self.clear()
            self._status.setText(
                (storage or {}).get("error")
                or "No device connected."
            )
            return

        for key, label in self._info_labels.items():
            label.setText(info.get(key, "—") or "—")

        self._apply_battery(battery or {})
        self._apply_storage(storage or {})

        if storage and not storage.get("available"):
            self._status.setText(
                storage.get("error") or "Loaded — storage details unavailable."
            )
        else:
            self._status.setText("Loaded.")

    def _apply_battery(self, battery: dict):
        if not battery.get("available"):
            self._bat_pct.setText("—")
            self._bat_status.setText("")
            self._bat_bar.setValue(0)
            for label in self._bat_labels.values():
                label.setText("—")
                label.setToolTip("")
            return

        level = battery.get("level")
        self._bat_pct.setText(f"{level}%" if level is not None else "—")
        self._bat_bar.setValue(level if level is not None else 0)

        status = battery.get("status") or "Not reported"
        self._bat_status.setText(status)
        status_code = battery.get("status_code")
        self._bat_status.setToolTip(
            f"BatteryManager status code: {status_code}" if status_code is not None else ""
        )

        health = battery.get("health") or "Not reported"
        self._bat_labels["health"].setText(health)
        health_code = battery.get("health_code")
        self._bat_labels["health"].setToolTip(
            f"BatteryManager health code: {health_code}" if health_code is not None else ""
        )

        self._bat_labels["power"].setText(battery.get("power_source") or "—")

        voltage = battery.get("voltage_mv")
        self._bat_labels["voltage"].setText(
            f"{voltage / 1000:.2f} V" if voltage is not None else "—"
        )

        temperature = battery.get("temperature_c")
        self._bat_labels["temperature"].setText(
            f"{temperature:.1f} °C" if temperature is not None else "—"
        )

        self._bat_labels["technology"].setText(battery.get("technology") or "—")

        charge = battery.get("charge_counter_mah")
        self._bat_labels["charge"].setText(
            f"{charge:,.0f} mAh" if charge is not None else "—"
        )

        full = battery.get("max_capacity_mah")
        design = battery.get("design_capacity_mah")
        if full is not None and design is not None:
            capacity = f"{full:,.0f} mAh (design {design:,.0f})"
        elif full is not None:
            capacity = f"{full:,.0f} mAh"
        elif design is not None:
            capacity = f"{design:,.0f} mAh"
        else:
            capacity = "—"
        self._bat_labels["capacity"].setText(capacity)

    def _apply_storage(self, storage: dict):
        self._clear_external_sections()

        if not storage.get("available"):
            self._int_heading.setText("Internal storage")
            self._int_bar.setValue(0)
            self._int_usage.setText("—")
            self._int_health.setText("Health: —")
            self._int_eol.setText("Pre-EOL: —")
            self._int_meta.setText("")
            self._ext_sep.setVisible(False)
            self._ext_container.setVisible(False)
            return

        internal = storage.get("internal") or {}
        kind = internal.get("kind") or "Internal storage"
        self._int_heading.setText(f"Internal storage  ·  {kind}")
        self._int_usage.setText(self._usage_text(internal))
        self._int_bar.setValue(internal.get("used_pct") or 0)

        health = internal.get("health")
        if health:
            self._int_health.setText(f"Health: {health['code']} ({health['note']})")
            self._int_health.setToolTip(
                "Raw storage life-time code reported by the device; "
                "the bracketed text is the JEDEC interpretation."
            )
        elif internal.get("health_requires_root"):
            self._int_health.setText("Health: requires root access")
            self._int_health.setToolTip(
                "The eMMC/UFS wear counters are root-only on most Android devices."
            )
        else:
            self._int_health.setText("Health: not reported by device")
            self._int_health.setToolTip("")

        eol = internal.get("eol")
        if eol:
            self._int_eol.setText(f"Pre-EOL: {eol['code']} ({eol['note']})")
        elif internal.get("eol_requires_root"):
            self._int_eol.setText("Pre-EOL: requires root access")
        else:
            self._int_eol.setText("Pre-EOL: not reported")

        meta: list[str] = []
        if internal.get("name"):
            meta.append(f"Chip: {internal['name']}")
        if internal.get("date"):
            meta.append(f"Manufactured: {internal['date']}")
        self._int_meta.setText("  ·  ".join(meta))
        self._int_meta.setVisible(bool(meta))

        external = storage.get("external") or []
        for volume in external:
            self._ext_layout.addWidget(self._make_external_section(volume))
        self._ext_sep.setVisible(bool(external))
        self._ext_container.setVisible(bool(external))

    def _make_external_section(self, volume: dict) -> QWidget:
        frame = QWidget()
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        kind = volume.get("kind") or "Removable storage"
        label = volume.get("label") or ""
        heading = QLabel(f"{kind}  ·  {label}" if label else kind)
        heading_font = QFont()
        heading_font.setBold(True)
        heading_font.setPointSize(10)
        heading.setFont(heading_font)
        lay.addWidget(heading)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        bar.setValue(volume.get("used_pct") or 0)
        lay.addWidget(bar)

        usage = QLabel(self._usage_text(volume))
        usage.setWordWrap(True)
        usage.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(usage)

        health = volume.get("health")
        if health:
            health_text = f"Health: {health['code']} ({health['note']})"
        else:
            health_text = "Health: not reported by this card"
        health_lbl = QLabel(health_text)
        health_lbl.setWordWrap(True)
        lay.addWidget(health_lbl)

        meta: list[str] = []
        if volume.get("uuid"):
            meta.append(f"Volume {volume['uuid']}")
        if volume.get("fs_type"):
            meta.append(volume["fs_type"])
        meta_lbl = QLabel("  ·  ".join(meta))
        meta_lbl.setObjectName("mutedLabel")
        meta_lbl.setWordWrap(True)
        meta_lbl.setVisible(bool(meta))
        lay.addWidget(meta_lbl)
        return frame

    def _clear_external_sections(self):
        while self._ext_layout.count():
            item = self._ext_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    @staticmethod
    def _usage_text(volume: dict) -> str:
        bits: list[str] = []
        used = volume.get("used")
        total = volume.get("total")
        free = volume.get("free")
        used_pct = volume.get("used_pct")
        if used and total:
            bits.append(f"{used} used of {total}")
        elif total:
            bits.append(f"{total} total")
        if free:
            bits.append(f"{free} free")
        if used_pct is not None:
            bits.append(f"{used_pct}% used")
        return "  ·  ".join(bits) if bits else "Not reported"

    # ── Actions ─────────────────────────────────────────────────────────────
    def _make_reboot_handler(self, mode: str):
        def handler():
            ok, msg = adb.reboot(mode)
            self.log_message.emit(f"Reboot {mode or 'system'}: {msg}")
            self._status.setText(msg)
        return handler

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

    def clear(self):
        for label in self._info_labels.values():
            label.setText("—")
        self._apply_battery({})
        self._apply_storage({})
        self._status.setText("No device connected.")

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
