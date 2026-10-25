# ADB Manager

A desktop app for managing Android phones over ADB, built with PyQt6. It runs on Windows and Linux. Everything happens through a tabbed window, so you don't have to remember `adb` commands.

What it does:

- **Wireless connection.** It can start a Wi-Fi hotspot on your PC and show a QR code for the phone to scan. After that you can pair, connect manually by IP and port, or let the app find the phone for you (it tries mDNS and an ARP scan at the same time).
- **Automatic device detection.** Every 2 seconds it checks for connected, disconnected, unauthorized and offline devices.
- **Package manager.** Lists installed apps with readable names from a local database. You can remove, restore, disable, enable, suspend and force-stop apps, and look up unfamiliar ones online.
- **Sideloading.** Install `.apk` files and split-APK bundles (`.xapk`, `.apkm`, `.apks`, `.apkx`). Drag and drop works.
- **Process monitor.** Live process list with CPU and memory per process, a filter box, auto-refresh, and kill with or without root.
- **Terminal.** An ADB shell with command history, a root toggle, and a sidebar of quick commands you can add to.
- **File manager.** Browse the device filesystem (including `/data` and `/system` with root), and pull, push or delete files.
- **Device info.** Model and build details, battery status and health, internal and microSD storage, screenshots, and reboot buttons.
- **Light and dark themes.** Toggle from the header. Your choice and window size are saved.

An **Action Log** panel at the bottom records what the app has done during the session; not verbose.

---

## Quick start

You need Python 3.10 or newer.

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Get ADB

Download [Android Platform Tools](https://developer.android.com/studio/releases/platform-tools). Then do one of these:

- Put `adb` (Linux) or `adb.exe` (Windows) in the same folder as `main.py`, or
- Add it to your system `PATH`.

### 3. Run

```bash
python main.py
```

---

## Connecting your phone

The Connect tab shows connected devices and checks for changes every 2 seconds. The **Refresh** button is only there if you don't want to wait.

### Wirelessly, using the app

1. Open the **Connect** tab.
2. Enter an SSID and password, or leave them blank. The default SSID is `ADB-Manager` and a random password is generated for you.
3. Click **Create Hotspot & Show QR**, then scan the code with your phone to join the network.
4. On the phone, go to Developer options → Wireless debugging and note the IP address and port.
5. Enter the IP and port in the app and click **Connect**. Or click **Find Phone & Connect** and let it search.

On Android 11 and newer you may need to pair first. Choose "Pair device with pairing code" on the phone, enter the pairing port and the 6-digit code in the app, and click **Pair**. Then connect as above.

### Wirelessly, without the hotspot

If your phone and PC are already on the same network, skip steps 2 and 3. Pair and connect from the app, or run `adb connect` yourself in a terminal. The device shows up on its own within a few seconds.

### USB

Plug the phone in with USB debugging enabled and accept the prompt on the phone. It shows up on its own.

---

## Package name database

Android lists apps by package name, like `com.samsung.android.bixby.agent`, which doesn't tell you much. The app ships with a database that maps those names to readable ones. It currently holds about 6,000 packages, and around 4,500 of them have a readable name. Packages the database doesn't know are shown in grey as `[com.example.app]`.

**Where it lives**

- Running from source: `data/packages.json`
- Standalone build: a per-user copy that is created from the bundled one on first launch:
  - Windows: `%LOCALAPPDATA%\ADB Manager\packages.json`
  - Linux: `${XDG_DATA_HOME:-~/.local/share}/ADB Manager/packages.json`
  - macOS: `~/Library/Application Support/ADB Manager/packages.json` (macOS is not tested)

If the file is missing, the app recreates it from the bundled copy, or from a small built-in list if that is missing too.

**Growing it**

- **⬇ Update Name DB** downloads open-source package lists (UAD-NG and MuntashirAkon's android-debloat-list) and merges them in. If the download fails, your existing database is left alone.
- **📱 Names from Device** (highly recommend clicking this every time you connect a new device) asks the connected phone for the real app labels through Android's `PackageManager`. It uses a tiny helper (`assets/device_labels.dex`), so it works on newer Android versions where `dumpsys` no longer includes labels, and it doesn't need root. On older versions it falls back to parsing `dumpsys`.

Both buttons only add or update entries. Names you already have are never thrown away, so the database keeps growing.

---

## Package actions

Most actions don't need root. If one fails without it, the app tries again with `su` where that makes sense.

|        Button       |          What it runs           | Root?                           |
|---------------------|---------------------------------|---------------------------------|
|   Remove for User   | `pm uninstall -k --user 0`      | No                              |
|   Restore for User  | `pm install-existing --user 0`  | No                              |
|   Disable / Enable  | `pm disable-user` / `pm enable` | Not usually; fallback uses root |
| Suspend / Unsuspend | `pm suspend` / `pm unsuspend`   | No                              |
|     Force Stop      | `am force-stop`                 | No                              |
|   Uninstall (root)  | `pm uninstall`                  | Needed for system apps          |

"Remove for User" keeps the app on the system partition and just removes it for your user, so you can bring it back with "Restore for User". Even with this, be careful with system packages as removing the wrong one can break important features or Wi-Fi, which may interrupt the ADB connection and cause a major headache.

---

## Root features

Root is detected automatically. Without it the app still works for everything except:

- Uninstalling system apps completely (Removing them for user works fine, which is what I recommend doing even if you have a rooted device)
- Browsing protected folders like `/data` in the file manager
- Killing protected processes
- Reading eMMC/UFS wear counters from sysfs; I made a fallback attempt for non-rooted devices but it'll fail in most cases. Storage type, capacity, usage and microSD stats work either way.

---

## Platform notes

| Platform | Hotspot | Notes |
|----------|---------|-------|
| Windows  | `netsh wlan hostednetwork` | Needs admin rights, and your Wi-Fi driver has to support hosted networks. Many newer adapters don't. |
| Linux    | `nmcli` (NetworkManager) | NetworkManager must be installed |
| macOS    | Not supported | You can still connect manually, or by USB |

If the hotspot doesn't work on your machine, you can still connect over an existing network or USB.

---

## Building a standalone executable

```bash
pip install pyinstaller
# Put adb / adb.exe next to build.spec first
pyinstaller build.spec
```

The result is `dist/ADBManager` on Linux or `dist/ADBManager.exe` on Windows. It's a single file with the package database, assets and `adb` (if you placed it next to `build.spec`) bundled inside. User data is stored in the per-user folder listed above, so it survives moving or replacing the executable.

If you add `assets/icon.png` (window icon) or `assets/icon.ico` (executable icon), they are picked up automatically.

---

## Project layout

```
.
├── main.py               # Entry point
├── build.spec            # PyInstaller spec
├── requirements.txt
├── collect_packages.py   # Package-name database builder
├── core/
│   ├── adb.py            # All ADB calls
│   ├── package_db.py     # Local package → name database
│   ├── phone_finder.py   # mDNS / ARP device discovery
│   └── hotspot_qr.py     # Hotspot creation and QR code
├── ui/
│   ├── main_window.py    # Main window, header, tabs, action log
│   ├── theme.py          # Light/dark palettes, styling, saved preference
│   ├── tab_connect.py    # Pairing, connecting, device list
│   ├── tab_packages.py   # Package manager
│   ├── tab_monitor.py    # Process/Resource monitor
│   ├── tab_terminal.py   # ADB shell
│   ├── tab_files.py      # File manager
│   ├── tab_sideload.py   # APK and bundle installer
│   └── tab_device.py     # Device info
├── data/
│   └── packages.json     # Local package database
├── tools/
│   └── device_labels/    # Java source and build notes for the label helper
└── assets/               # Checkbox/arrow images and device_labels.dex
```

---

## Adding a new tab

Each feature is its own `QWidget`. To add one:

**1. Create `ui/tab_myfeature.py`**

```python
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import pyqtSignal
from core import adb

class MyFeatureTab(QWidget):
    log_message = pyqtSignal(str)   # optional, shows up in the Action Log

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("My new feature"))
        # build the rest of your UI here
```

**2. Register it in `ui/main_window.py`**

```python
from ui.tab_myfeature import MyFeatureTab

# in MainWindow._build_ui(), next to the other tabs:
self._myfeature_tab = MyFeatureTab()
self.add_tab(self._myfeature_tab, "My Feature")

# optional: send its messages to the Action Log
self._myfeature_tab.log_message.connect(self._append_log)
```

## Personal data
Harvested package names stay on your device, and nothing else is harvested or sent anywhere.