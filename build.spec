# build.spec  —  Single-file executable, size-optimised
#
# Usage:
#   pip install pyinstaller pyqt6 qrcode pillow
#   pyinstaller build.spec
#
# Output: dist/ADBManager  (Linux/macOS)  or  dist/ADBManager.exe  (Windows)
#
# Place adb / adb.exe next to build.spec before building, or ensure
# it is on the user's PATH at runtime.

import sys
from pathlib import Path

HERE = Path(SPEC).parent

# ── ADB binary (optional bundle) ─────────────────────────────────────────────
_adb_name = "adb.exe" if sys.platform.startswith("win") else "adb"
_adb_src  = HERE / _adb_name
binaries  = [(str(_adb_src), ".")] if _adb_src.exists() else []

# ── Data files ────────────────────────────────────────────────────────────────
datas = [
    (str(HERE / "data"),               "data"),
    (str(HERE / "collect_packages.py"),"." ),
]
_assets = HERE / "assets"
if _assets.is_dir():
    datas.append((str(_assets), "assets"))

# ── Hidden imports (things PyInstaller misses) ────────────────────────────────
hiddenimports = [
    "PyQt6",
    "PyQt6.QtWidgets",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "qrcode",
    "qrcode.image.pil",
    "PIL",
    "PIL.Image",
    "PIL.PngImagePlugin",
    "collect_packages",
    "concurrent.futures",
    "zipfile",
    "tempfile",
    "shutil",
]

# ── Aggressive exclusions — unused Qt modules + scientific libs ───────────────
excludes = [
    # Other GUI toolkits
    "tkinter", "_tkinter",
    # Scientific (not used)
    "matplotlib", "numpy", "scipy", "pandas",
    # Qt modules we don't touch
    "PyQt6.QtBluetooth", "PyQt6.QtNfc", "PyQt6.QtSql",
    "PyQt6.QtDesigner", "PyQt6.QtHelp",
    "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets",
    "PyQt6.QtOpenGL", "PyQt6.QtOpenGLWidgets",
    "PyQt6.QtPdf", "PyQt6.QtPdfWidgets",
    "PyQt6.QtPositioning", "PyQt6.QtPrintSupport",
    "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtQuickWidgets",
    "PyQt6.QtRemoteObjects", "PyQt6.QtSensors", "PyQt6.QtSerialPort",
    "PyQt6.QtSvg", "PyQt6.QtSvgWidgets", "PyQt6.QtTest",
    "PyQt6.QtWebChannel", "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebSockets",
    "PyQt6.Qt3DAnimation", "PyQt6.Qt3DCore", "PyQt6.Qt3DExtras",
    "PyQt6.Qt3DInput", "PyQt6.Qt3DLogic", "PyQt6.Qt3DRender",
    # Pillow formats we don't need
    "PIL.ImageFilter", "PIL.ImageEnhance", "PIL.ImageOps",
    "PIL.BmpImagePlugin", "PIL.GifImagePlugin",
    "PIL.JpegImagePlugin", "PIL.TiffImagePlugin",
    # Unused stdlib
    "html", "xml", "xmlrpc",
    "ftplib", "imaplib", "poplib", "smtplib",
    "telnetlib", "nntplib",
    "curses", "readline", "rlcompleter",
    "distutils", "lib2to3",
    "unittest", "doctest", "pdb",
    "antigravity", "this",
]

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    [str(HERE / "main.py")],
    pathex=[str(HERE)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

# ── Strip duplicate/unneeded Qt platform plugins ──────────────────────────────
# Keep only the platform plugin for the current OS + the minimal set
def _keep_binary(name: str) -> bool:
    name_l = name.lower()
    # Always keep
    if any(x in name_l for x in ("qt6core", "qt6gui", "qt6widgets", "qt6network")):
        return True
    # Platform plugins: keep xcb (Linux), cocoa (macOS), windows (Win), minimal
    if "platforms" in name_l:
        keep_platforms = {"xcb", "cocoa", "qwindows", "minimal", "offscreen"}
        return any(p in name_l for p in keep_platforms)
    # Styles: only fusion (our light/dark themes use it)
    if "styles" in name_l:
        return "fusion" in name_l
    # Image formats: only png (for QR codes)
    if "imageformats" in name_l:
        return "qpng" in name_l or "qico" in name_l
    return True

a.binaries = TOC(
    [(name, path, kind)
     for name, path, kind in a.binaries
     if _keep_binary(name)]
)

pyz = PYZ(a.pure)

# ── Single-file EXE ───────────────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ADBManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,          # strip debug symbols from binaries
    upx=True,            # compress with UPX if available (install: https://upx.github.io)
    upx_exclude=[
        # Don't UPX-compress Qt libs — they don't compress well and can corrupt
        "Qt6Core*", "Qt6Gui*", "Qt6Widgets*",
        "libQt6*", "qt6*",
    ],
    runtime_tmpdir=None,
    console=False,       # no terminal window; set True for debug output
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(HERE / "assets" / "icon.ico") if (HERE / "assets" / "icon.ico").exists() else None,
)
