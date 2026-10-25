"""Central light/dark theme and stylesheet for the application."""

from pathlib import Path
from string import Template

from PyQt6.QtCore import QObject, QSettings, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication


PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "window": "#0e1117",
        "surface": "#161a23",
        "surface_alt": "#1d2230",
        "surface_hover": "#272e3f",
        "border": "#2a3142",
        "border_strong": "#3b455b",
        "text": "#e7eaf3",
        "muted": "#9aa4b8",
        "subtle": "#6b7487",
        "accent": "#7c6cf0",
        "accent_hover": "#8f80ff",
        "accent_text": "#ffffff",
        "accent_soft": "#272140",
        "accent_border": "#4c3f87",
        "success": "#4ade80",
        "warning": "#fbbf24",
        "danger": "#fb7185",
        "info": "#60a5fa",
        "cyan": "#22d3ee",
        "selection": "#34305a",
        "selection_text": "#f1edff",
        "console_bg": "#0b0e14",
        "console_text": "#d8dee9",
    },
    "light": {
        "window": "#f3f5fa",
        "surface": "#ffffff",
        "surface_alt": "#eef1f7",
        "surface_hover": "#e2e7f1",
        "border": "#d8deea",
        "border_strong": "#b9c3d6",
        "text": "#1b2333",
        "muted": "#5f6b80",
        "subtle": "#8892a4",
        "accent": "#5b45d6",
        "accent_hover": "#4934bd",
        "accent_text": "#ffffff",
        "accent_soft": "#ede9ff",
        "accent_border": "#c9c0ff",
        "success": "#15803d",
        "warning": "#a16207",
        "danger": "#dc2626",
        "info": "#2563eb",
        "cyan": "#0e7490",
        "selection": "#ddd6fe",
        "selection_text": "#2e1065",
        "console_bg": "#f8fafc",
        "console_text": "#1f2937",
    },
}


_QSS_TEMPLATE = Template("""
* {
    font-family: "Segoe UI", "Segoe UI Variable", "Inter", "Ubuntu", "Noto Sans", "DejaVu Sans", sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog, QMessageBox {
    background-color: ${window};
}
QWidget {
    color: ${text};
}
QLabel {
    background: transparent;
}
QWidget#appHeader {
    background-color: ${surface};
    border: 1px solid ${border};
    border-radius: 12px;
}
QLabel#appTitle {
    font-size: 21px;
    font-weight: bold;
    color: ${text};
}
QLabel#appSubtitle {
    font-size: 11px;
    color: ${muted};
}
QLabel#sectionLabel {
    color: ${accent};
    font-size: 12px;
    font-weight: bold;
}
QLabel#hintLabel {
    color: ${muted};
    font-size: 11px;
}
QLabel#smallLabel {
    color: ${muted};
    font-size: 11px;
}
QLabel#mutedLabel {
    color: ${muted};
}
QLabel#statusLabel {
    color: ${muted};
    background-color: ${surface_alt};
    border: 1px solid ${border};
    border-radius: 8px;
    padding: 6px 10px;
    font-weight: bold;
}
QLabel#statusLabel[tone="success"] {
    color: ${success};
}
QLabel#statusLabel[tone="info"] {
    color: ${accent};
}
QLabel#statusLabel[tone="danger"] {
    color: ${danger};
}
QLabel#qrPlaceholder {
    color: ${subtle};
}
QTabWidget::pane {
    background-color: ${surface};
    border: 1px solid ${border};
    border-radius: 12px;
    top: -1px;
}
QTabWidget::tab-bar {
    alignment: left;
}
QTabBar {
    qproperty-drawBase: 0;
    background: transparent;
}
QTabBar::tab {
    background: transparent;
    color: ${muted};
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 7px 15px;
    margin: 2px 3px 6px 0;
}
QTabBar::tab:hover:!selected {
    background-color: ${surface_alt};
    color: ${text};
}
QTabBar::tab:selected {
    background-color: ${accent_soft};
    color: ${accent};
    border-color: ${accent_border};
}
QPushButton {
    background-color: ${surface_alt};
    color: ${text};
    border: 1px solid ${border};
    border-radius: 8px;
    padding: 6px 13px;
    min-height: 18px;
}
QPushButton:hover {
    background-color: ${surface_hover};
    border-color: ${accent_border};
}
QPushButton:pressed {
    background-color: ${accent_soft};
    border-color: ${accent};
}
QPushButton:focus {
    border-color: ${accent};
}
QPushButton:disabled {
    background-color: ${surface};
    color: ${subtle};
    border-color: ${border};
}
QPushButton#primaryButton {
    background-color: ${accent};
    color: ${accent_text};
    border-color: ${accent};
    font-weight: bold;
}
QPushButton#primaryButton:hover {
    background-color: ${accent_hover};
    border-color: ${accent_hover};
}
QPushButton#primaryButton:pressed {
    background-color: ${accent};
}
QPushButton#themeToggle {
    background-color: ${surface_alt};
    color: ${text};
    border: 1px solid ${border};
    border-radius: 9px;
    padding: 6px 12px;
    font-weight: bold;
}
QPushButton#themeToggle:hover {
    background-color: ${accent_soft};
    border-color: ${accent_border};
    color: ${accent};
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit,
QListWidget, QTreeWidget, QTableWidget {
    background-color: ${surface};
    color: ${text};
    border: 1px solid ${border};
    border-radius: 8px;
    padding: 5px 8px;
    selection-background-color: ${selection};
    selection-color: ${selection_text};
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
QTextEdit:focus, QPlainTextEdit:focus {
    border-color: ${accent};
}
QLineEdit:disabled, QSpinBox:disabled, QTextEdit:disabled {
    color: ${subtle};
    background-color: ${surface_alt};
}
QSpinBox, QDoubleSpinBox {
    padding-right: 25px;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 22px;
    height: 14px;
    border-left: 1px solid ${border};
    border-top-right-radius: 7px;
    background-color: ${surface_alt};
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 22px;
    height: 14px;
    border-left: 1px solid ${border};
    border-top: 1px solid ${border};
    border-bottom-right-radius: 7px;
    background-color: ${surface_alt};
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: ${surface_hover};
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url("${arrow_up}");
    width: 8px;
    height: 8px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url("${arrow_down}");
    width: 8px;
    height: 8px;
}
QScrollArea {
    background: transparent;
    border: none;
}
QGroupBox {
    background-color: ${surface};
    border: 1px solid ${border};
    border-radius: 10px;
    margin-top: 15px;
    padding: 12px 10px 10px 10px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 6px;
    color: ${muted};
    background-color: ${window};
}
QHeaderView::section {
    background-color: ${surface_alt};
    color: ${muted};
    border: none;
    border-bottom: 1px solid ${border};
    padding: 7px 8px;
    font-weight: bold;
}
QTableCornerButton::section {
    background-color: ${surface_alt};
    border: none;
}
QTableWidget, QTreeWidget, QListWidget {
    alternate-background-color: ${surface_alt};
    gridline-color: ${border};
    outline: 0;
}
QTableWidget::item, QTreeWidget::item, QListWidget::item {
    padding: 5px 7px;
    border: none;
}
QTableWidget::item:selected, QTreeWidget::item:selected, QListWidget::item:selected {
    background-color: ${selection};
    color: ${selection_text};
}
QTableWidget::item:hover, QTreeWidget::item:hover, QListWidget::item:hover {
    background-color: ${surface_hover};
}
QCheckBox {
    color: ${text};
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid ${border_strong};
    border-radius: 4px;
    background-color: ${surface};
}
QCheckBox::indicator:hover {
    border-color: ${accent};
}
QCheckBox::indicator:checked {
    background-color: ${accent};
    border-color: ${accent};
    image: url("${check_icon}");
}
QCheckBox::indicator:checked:hover {
    background-color: ${accent_hover};
    border-color: ${accent_hover};
}
QProgressBar {
    background-color: ${surface_alt};
    border: 1px solid ${border};
    border-radius: 5px;
    text-align: center;
    color: ${muted};
}
QProgressBar::chunk {
    background-color: ${accent};
    border-radius: 4px;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: ${border_strong};
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: ${accent};
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: ${border_strong};
    border-radius: 4px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover {
    background: ${accent};
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}
QStatusBar {
    background-color: transparent;
    color: ${muted};
    border-top: 1px solid ${border};
    padding: 3px 6px;
}
QStatusBar::item {
    border: none;
}
QDockWidget {
    color: ${muted};
}
QDockWidget::title {
    background-color: ${surface_alt};
    border: 1px solid ${border};
    border-radius: 6px;
    padding: 5px 8px;
    text-align: left;
}
QMenu {
    background-color: ${surface};
    color: ${text};
    border: 1px solid ${border};
    border-radius: 8px;
    padding: 5px;
}
QMenu::item {
    padding: 7px 24px 7px 16px;
    border-radius: 5px;
    margin: 1px 3px;
}
QMenu::item:selected {
    background-color: ${accent_soft};
    color: ${accent};
}
QMenu::separator {
    height: 1px;
    background-color: ${border};
    margin: 4px 8px;
}
QToolTip {
    background-color: ${surface_alt};
    color: ${text};
    border: 1px solid ${border_strong};
    border-radius: 6px;
    padding: 5px 7px;
}
QSplitter::handle {
    background-color: ${border};
}
QSplitter::handle:hover {
    background-color: ${accent};
}
QFrame#statCard {
    background-color: ${surface_alt};
    border: 1px solid ${border};
    border-radius: 10px;
}
QLabel#statLabel {
    color: ${muted};
    font-size: 10px;
    font-weight: bold;
}
QLabel#statSub {
    color: ${subtle};
    font-size: 10px;
}
QTextEdit#logView {
    background-color: ${console_bg};
    color: ${console_text};
    border: 1px solid ${border};
    border-radius: 8px;
    padding: 6px;
    font-family: "Cascadia Mono", Consolas, "DejaVu Sans Mono", "Liberation Mono", monospace;
    font-size: 11px;
}
QTextEdit#terminalOutput, QLineEdit#terminalInput {
    background-color: ${console_bg};
    color: ${console_text};
    border: 1px solid ${border};
    border-radius: 8px;
    font-family: "Cascadia Mono", Consolas, "DejaVu Sans Mono", "Liberation Mono", monospace;
}
QTextEdit#terminalOutput {
    padding: 8px;
}
QLineEdit#terminalInput {
    padding: 7px 9px;
}
QTextEdit#terminalOutput:focus, QLineEdit#terminalInput:focus {
    border-color: ${accent};
}
""")


_ASSETS = Path(__file__).resolve().parent.parent / "assets"


def _asset_url(name: str, fallback: str) -> str:
    path = _ASSETS / name
    return path.as_posix() if path.is_file() else fallback


def build_stylesheet(colors: dict[str, str]) -> str:
    values = dict(colors)
    values["check_icon"] = _asset_url(
        "check.png",
        ":/qt-project.org/styles/commonstyle/images/standardbutton-apply-16.png",
    )
    values["arrow_up"] = _asset_url(
        "arrow-up.png",
        ":/qt-project.org/styles/commonstyle/images/arrow-up-16.png",
    )
    values["arrow_down"] = _asset_url(
        "arrow-down.png",
        ":/qt-project.org/styles/commonstyle/images/arrow-down-16.png",
    )
    return _QSS_TEMPLATE.substitute(values)


def _build_palette(colors: dict[str, str]) -> QPalette:
    palette = QPalette()
    role_map = {
        QPalette.ColorRole.Window: "window",
        QPalette.ColorRole.WindowText: "text",
        QPalette.ColorRole.Base: "surface",
        QPalette.ColorRole.AlternateBase: "surface_alt",
        QPalette.ColorRole.Text: "text",
        QPalette.ColorRole.Button: "surface_alt",
        QPalette.ColorRole.ButtonText: "text",
        QPalette.ColorRole.Highlight: "selection",
        QPalette.ColorRole.HighlightedText: "selection_text",
        QPalette.ColorRole.ToolTipBase: "surface_alt",
        QPalette.ColorRole.ToolTipText: "text",
        QPalette.ColorRole.PlaceholderText: "subtle",
        QPalette.ColorRole.Link: "accent",
    }
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        for role, key in role_map.items():
            palette.setColor(group, role, QColor(colors[key]))
    for role, key in role_map.items():
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors[key]))
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(colors["subtle"]))
    return palette


def mono_font(size: int = 10, bold: bool = False) -> QFont:
    font = QFont()
    font.setFamilies([
        "Cascadia Mono", "Consolas", "DejaVu Sans Mono",
        "Liberation Mono", "Courier New",
    ])
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setFixedPitch(True)
    font.setPointSize(size)
    if bold:
        font.setWeight(QFont.Weight.DemiBold)
    return font


class ThemeManager(QObject):
    changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._name = "dark"
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        settings = QSettings("adb-manager", "ADB Manager")
        name = settings.value("ui/theme", "dark")
        self._name = name if name in PALETTES else "dark"
        self._loaded = True

    @property
    def name(self) -> str:
        self.load()
        return self._name

    @property
    def colors(self) -> dict[str, str]:
        return PALETTES[self.name]

    def color(self, key: str) -> str:
        return self.colors[key]

    def qcolor(self, key: str) -> QColor:
        return QColor(self.colors[key])

    def apply(self) -> None:
        self.load()
        app = QApplication.instance()
        if app is None:
            return
        app.setPalette(_build_palette(self.colors))
        app.setStyleSheet(build_stylesheet(self.colors))

    def set_theme(self, name: str) -> None:
        if name not in PALETTES:
            raise ValueError(f"Unknown theme: {name}")
        self.load()
        changed = name != self._name
        self._name = name
        self.apply()
        if changed:
            QSettings("adb-manager", "ADB Manager").setValue("ui/theme", name)
            self.changed.emit(name)

    def toggle(self) -> None:
        self.set_theme("light" if self.name == "dark" else "dark")


theme = ThemeManager()
