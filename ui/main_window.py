from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QStatusBar, QDockWidget, QTextEdit, QLabel, QPushButton,
)
from PyQt6.QtCore import Qt, QSettings

from ui.theme import mono_font, theme
from ui.tab_connect  import ConnectTab
from ui.tab_packages import PackagesTab
from ui.tab_monitor  import MonitorTab
from ui.tab_terminal import TerminalTab
from ui.tab_files    import FilesTab
from ui.tab_device   import DeviceTab
from ui.tab_sideload import SideloadTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ADB Manager")
        self.resize(1220, 800)
        self.setMinimumSize(980, 680)
        self._connected_serials: set[str] = set()

        theme.apply()
        self._build_ui()
        theme.changed.connect(self._on_theme_changed)
        self._sync_theme_button()
        self._restore_geometry()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 14, 14, 10)
        layout.setSpacing(10)

        header = QWidget()
        header.setObjectName("appHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 12, 10)
        header_layout.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title = QLabel("ADB Manager")
        title.setObjectName("appTitle")
        subtitle = QLabel("Android device toolkit")
        subtitle.setObjectName("appSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        self._theme_btn = QPushButton()
        self._theme_btn.setObjectName("themeToggle")
        self._theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_btn.setMinimumWidth(104)
        self._theme_btn.clicked.connect(theme.toggle)
        header_layout.addWidget(self._theme_btn)
        layout.addWidget(header)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs, stretch=1)

        self._connect_tab  = ConnectTab()
        self._packages_tab = PackagesTab()
        self._monitor_tab  = MonitorTab()
        self._terminal_tab = TerminalTab()
        self._files_tab    = FilesTab()
        self._sideload_tab = SideloadTab()
        self._device_tab   = DeviceTab()

        self.add_tab(self._connect_tab,   "Connect")
        self.add_tab(self._packages_tab,  "Packages")
        self.add_tab(self._monitor_tab,   "Monitor")
        self.add_tab(self._terminal_tab,  "Terminal")
        self.add_tab(self._files_tab,     "Files")
        self.add_tab(self._sideload_tab,  "Sideload")
        self.add_tab(self._device_tab,    "Device")

        self._connect_tab.device_connected.connect(self._on_device_connected)
        self._connect_tab.device_disconnected.connect(self._on_device_disconnected)
        for tab in [self._packages_tab, self._monitor_tab, self._terminal_tab,
                    self._files_tab, self._sideload_tab, self._device_tab]:
            if hasattr(tab, "log_message"):
                tab.log_message.connect(self._append_log)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready — no device connected")

        dock = QDockWidget("Action Log", self)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self._log_view = QTextEdit()
        self._log_view.setObjectName("logView")
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumHeight(90)
        self._log_view.document().setMaximumBlockCount(500)
        self._log_view.setFont(mono_font(9))
        dock.setWidget(self._log_view)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        self.resizeDocks([dock], [112], Qt.Orientation.Vertical)

    def add_tab(self, widget: QWidget, label: str) -> int:
        return self._tabs.addTab(widget, label)

    def _sync_theme_button(self):
        if theme.name == "dark":
            self._theme_btn.setText("Light mode")
            self._theme_btn.setToolTip("Switch to light mode")
        else:
            self._theme_btn.setText("Dark mode")
            self._theme_btn.setToolTip("Switch to dark mode")

    def _on_theme_changed(self, _name: str):
        self._sync_theme_button()

    def _restore_geometry(self):
        settings = QSettings("adb-manager", "ADB Manager")
        geometry = settings.value("ui/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def _on_device_connected(self, serial: str):
        self._connected_serials.add(serial)
        self._status_bar.showMessage(self._connection_status())
        self._append_log(f"Connected: {serial}")
        self._device_tab.refresh()

    def _on_device_disconnected(self, serial: str):
        self._connected_serials.discard(serial)
        self._status_bar.showMessage(self._connection_status())
        self._append_log(f"Disconnected: {serial}")
        if not self._connected_serials:
            self._device_tab.clear()

    def _connection_status(self) -> str:
        if not self._connected_serials:
            return "Ready — no device connected"
        if len(self._connected_serials) == 1:
            return f"✓ Connected: {next(iter(self._connected_serials))}"
        return f"✓ Connected: {len(self._connected_serials)} devices"

    def closeEvent(self, event):
        self._connect_tab.stop_polling()
        self._monitor_tab.shutdown()
        QSettings("adb-manager", "ADB Manager").setValue(
            "ui/geometry", self.saveGeometry()
        )
        super().closeEvent(event)

    def _append_log(self, msg: str):
        self._log_view.append(msg)
