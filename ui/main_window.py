from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTabWidget,
    QStatusBar, QDockWidget, QTextEdit,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ui.tab_connect  import ConnectTab
from ui.tab_packages import PackagesTab
from ui.tab_monitor  import MonitorTab
from ui.tab_terminal import TerminalTab
from ui.tab_files    import FilesTab
from ui.tab_device   import DeviceTab
from ui.tab_sideload import SideloadTab


STYLESHEET = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', 'SF Pro Display', Ubuntu, sans-serif;
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #313244;
    border-radius: 4px;
}
QTabBar::tab {
    background: #181825;
    color: #a6adc8;
    padding: 8px 18px;
    border: 1px solid #313244;
    border-bottom: none;
    border-radius: 4px 4px 0 0;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #1e1e2e;
    color: #cba6f7;
    border-bottom: 2px solid #cba6f7;
}
QTabBar::tab:hover:!selected {
    background: #313244;
}
QPushButton {
    background: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 5px 12px;
}
QPushButton:hover {
    background: #45475a;
    border-color: #cba6f7;
}
QPushButton:pressed {
    background: #181825;
}
QPushButton:disabled {
    color: #585b70;
    border-color: #313244;
}
QLineEdit, QSpinBox, QTextEdit, QListWidget, QTreeWidget, QTableWidget {
    background: #181825;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 3px;
    selection-background-color: #45475a;
}
QLineEdit:focus, QSpinBox:focus {
    border-color: #cba6f7;
}
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 12px;
    padding: 6px;
    color: #a6e3a1;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QHeaderView::section {
    background: #313244;
    color: #cdd6f4;
    border: none;
    padding: 4px;
    border-right: 1px solid #45475a;
}
QTableWidget, QTreeWidget, QListWidget {
    alternate-background-color: #252535;
    gridline-color: #313244;
}
QTableWidget::item:selected, QTreeWidget::item:selected, QListWidget::item:selected {
    background: #45475a;
    color: #cdd6f4;
}
QCheckBox {
    color: #cdd6f4;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #45475a;
    border-radius: 3px;
    background: #181825;
}
QCheckBox::indicator:checked {
    background: #cba6f7;
    border-color: #cba6f7;
}
QProgressBar {
    background: #181825;
    border: 1px solid #45475a;
    border-radius: 3px;
    text-align: center;
}
QProgressBar::chunk {
    background: #cba6f7;
    border-radius: 2px;
}
QScrollBar:vertical {
    background: #181825;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #45475a;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar:horizontal {
    background: #181825;
    height: 8px;
}
QScrollBar::handle:horizontal {
    background: #45475a;
    border-radius: 4px;
}
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QStatusBar {
    background: #181825;
    color: #a6adc8;
    border-top: 1px solid #313244;
}
QDockWidget {
    color: #a6adc8;
    titlebar-close-icon: none;
}
QDockWidget::title {
    background: #313244;
    padding: 4px;
}
QMenu {
    background: #1e1e2e;
    border: 1px solid #45475a;
    border-radius: 4px;
}
QMenu::item {
    padding: 6px 20px;
}
QMenu::item:selected {
    background: #45475a;
}
QSplitter::handle {
    background: #45475a;
    width: 3px;
}
#statusLabel {
    color: #a6e3a1;
    font-weight: bold;
    padding: 4px 8px;
    border: 1px solid #313244;
    border-radius: 4px;
    background: #181825;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ADB Manager")
        self.resize(1200, 780)
        self.setStyleSheet(STYLESHEET)
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 0)
        layout.setSpacing(0)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        self._connect_tab  = ConnectTab()
        self._packages_tab = PackagesTab()
        self._monitor_tab  = MonitorTab()
        self._terminal_tab = TerminalTab()
        self._files_tab    = FilesTab()
        self._sideload_tab = SideloadTab()
        self._device_tab   = DeviceTab()

        self.add_tab(self._connect_tab,   "🔗  Connect")
        self.add_tab(self._packages_tab,  "📦  Packages")
        self.add_tab(self._monitor_tab,   "📊  Monitor")
        self.add_tab(self._terminal_tab,  "💻  Terminal")
        self.add_tab(self._files_tab,     "📁  Files")
        self.add_tab(self._sideload_tab,  "⚡  Sideload")
        self.add_tab(self._device_tab,    "ℹ  Device")

        self._connect_tab.device_connected.connect(self._on_device_connected)
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
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumHeight(120)
        mono = QFont("Courier New", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._log_view.setFont(mono)
        dock.setWidget(self._log_view)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)

    def add_tab(self, widget: QWidget, label: str) -> int:
        return self._tabs.addTab(widget, label)

    def _on_device_connected(self, serial: str):
        self._status_bar.showMessage(f"✓ Connected: {serial}")
        self._device_tab.refresh()

    def _append_log(self, msg: str):
        self._log_view.append(msg)
        doc = self._log_view.document()
        if doc.blockCount() > 500:
            cursor = self._log_view.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.select(cursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
