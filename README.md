# ADB Manager

A cross-platform (Windows and Linux) PyQt6 GUI for managing Android devices over ADB, featuring:

- **QR-code hotspot pairing** — creates a Wi-Fi hotspot on your pc, shows a QR code the phone scans to join the network and initiate ADB wireless pairing
- **Package manager** — list all installed apps with human-readable names from a local DB, uninstall/disable/enable with root, search online
- **Process monitor** — live view of running processes, auto-refresh, kill with or without root
- **ADB shell terminal** — interactive shell with command history, root toggle, and a quick-commands sidebar
- **File manager** — browse the full device filesystem (with root), pull/push/delete files
- **Device info** — model, build, battery, storage, screenshot, reboot controls

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Get ADB

Download [Android Platform Tools](https://developer.android.com/studio/releases/platform-tools) and either:
- Put `adb` (Linux/macOS) or `adb.exe` (Windows) **next to `main.py`**, or
- Add it to your system PATH

### 3. Run

```bash
python main.py
```

---

## Connecting Your Phone

### Method A — Using GUI

1. Open the **Connect** tab in the app
2. Set an SSID and optional password (or leave blank for auto-generated)
3. Click **Create Hotspot & Show QR**
4. On your phone: **Settings** → Developer Options → Wireless debugging → Note the IP address & Port and insert into the app
5. The app will detect the connection automatically

### Method B — Terminal

1. Connect via a terminal (with adb connect). The app will automatically detect it after it connects

### Method C — USB (legacy)

1. Connect phone via USB with USB debugging enabled
2. The app detects it automatically on the Connect tab

---

## Package Name Database

The first time you run the app, a seed database of ~200 well-known packages is written to `data/packages.json`.

To download a full database (~10,000+ packages):

1. Go to the **Packages** tab
2. Click **⬇ Update Name DB**
3. This downloads from open-source lists and saves locally — only needed once

Package names shown as `[com.example.app]` (grey, in brackets) are unknown to the DB.

---

## Building a Standalone Executable

```bash
pip install pyinstaller
# Place adb / adb.exe next to build.spec first
pyinstaller build.spec
```

Output: `dist/ADBManager/ADBManager` (Linux) or `dist/ADBManager/ADBManager.exe` (Windows)

The entire `dist/ADBManager/` folder is self-contained and portable.

---

## Adding New Features

Every feature is an isolated `QWidget` subclass. To add a new tab:

### 1. Create `ui/tab_myfeature.py`

```python
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import pyqtSignal
from core import adb

class MyFeatureTab(QWidget):
    log_message = pyqtSignal(str)   # optional — wires to global log

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("My new feature"))
        # ... build your UI
```

### 2. Register in `ui/main_window.py`

```python
from ui.tab_myfeature import MyFeatureTab

# In MainWindow._build_ui():
self._myfeature_tab = MyFeatureTab()
self.add_tab(self._myfeature_tab, "🔧  My Feature")

# Optionally wire logging:
self._myfeature_tab.log_message.connect(self._append_log)
```

That's it. No other files need to change.

---

## App Structure

```
adb_manager/
├── main.py               # Entry point
├── build.spec            # PyInstaller spec
├── requirements.txt
├── core/
│   ├── adb.py            # All ADB subprocess calls
│   ├── package_db.py     # Local package→name DB
│   └── hotspot_qr.py     # Hotspot creation + QR encoding
├── ui/
│   ├── main_window.py    # Main window + tab container
│   ├── tab_connect.py    # QR pairing tab
│   ├── tab_packages.py   # Package manager tab
│   ├── tab_monitor.py    # Process monitor tab
│   ├── tab_terminal.py   # ADB shell terminal tab
│   ├── tab_files.py      # File manager tab
│   └── tab_device.py     # Device info tab
├── data/
│   └── packages.json     # Local package name DB (auto-created)
└── assets/
    └── (optional for icons and stuff)
```

---

## Platform Notes

| Platform | Hotspot | Notes |
|----------|---------|-------|
| Windows  | ✓ `netsh hostednetwork` | Requires admin rights for hotspot |
| Linux    | ✓ `nmcli` / NetworkManager | Requires NetworkManager installed |
| macOS    | Might work but untested, not supported

---

## Root Features

The following actions require root on the phone:
- Disabling system packages (`pm disable-user`)
- Uninstalling system apps (`pm uninstall` via `su`)
- Browsing `/data`, `/system` in file manager
- Killing protected processes

Root is detected automatically. Non-root actions (user app uninstall, force-stop, etc.) work without root.
