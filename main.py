import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, "data")
os.makedirs(_DATA, exist_ok=True)

if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from core.package_db import ensure_db_exists
ensure_db_exists()

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from ui.main_window import MainWindow


def main():
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("ADB Manager")
    app.setApplicationDisplayName("ADB Manager")
    app.setOrganizationName("adb-manager")

    icon_path = os.path.join(_HERE, "assets", "icon.png")
    if os.path.isfile(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
