import os
import zipfile
import tempfile
import shutil
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QProgressBar, QTextEdit,
    QFileDialog, QCheckBox, QAbstractItemView, QGroupBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QTextCharFormat, QTextCursor

from core import adb
from ui.theme import mono_font, theme


class InstallWorker(QObject):
    progress = pyqtSignal(str, str)
    done     = pyqtSignal(str, bool, str)

    def __init__(self, jobs: list[dict], reinstall: bool, downgrade: bool):
        super().__init__()
        self.jobs      = jobs
        self.reinstall = reinstall
        self.downgrade = downgrade
    def run(self):
        for job in self.jobs:
            label = job["label"]
            path  = job["path"]
            ext   = job["type"]
            self.progress.emit(label, f"Installing {label}…")
            try:
                if ext == ".apk":
                    ok, msg = self._install_apk(path)
                else:
                    ok, msg = self._install_bundle(path)
                self.done.emit(label, ok, msg)
            except Exception as e:
                self.done.emit(label, False, str(e))

    def _install_apk(self, path: str) -> tuple[bool, str]:
        stdout, stderr, rc = adb.run(["install"] + self._flags() + [path], timeout=120)
        combined = (stdout + stderr).strip()
        ok = rc == 0 and "success" in combined.lower()
        return ok, combined

    def _install_bundle(self, path: str) -> tuple[bool, str]:
        tmpdir = tempfile.mkdtemp(prefix="adbmgr_")
        try:
            with zipfile.ZipFile(path, "r") as z:
                apk_members = [m for m in z.namelist() if m.lower().endswith(".apk")]
                if not apk_members:
                    return False, "No .apk files found inside the bundle."
                for member in apk_members:
                    filename = os.path.basename(member)
                    target   = os.path.join(tmpdir, filename)
                    with z.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)

            ordered = sorted(
                os.listdir(tmpdir),
                key=lambda n: (0 if n.lower() == "base.apk" else 1, n)
            )
            apk_paths = [os.path.join(tmpdir, n) for n in ordered]

            stdout, stderr, rc = adb.run(
                ["install-multiple"] + self._flags() + apk_paths,
                timeout=300,
            )
            combined = (stdout + stderr).strip()
            ok = rc == 0 and "success" in combined.lower()
            return ok, combined
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _flags(self) -> list[str]:
        flags = []
        if self.reinstall:
            flags.append("-r")
        if self.downgrade:
            flags.append("-d")
        return flags


SUPPORTED = (".apk", ".xapk", ".apkm", ".apks", ".apkx")


class DropList(QListWidget):
    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.toLocalFile().lower().endswith(SUPPORTED)
        ]
        if paths:
            self.files_dropped.emit(paths)
        event.acceptProposedAction()


class SideloadTab(QWidget):
    log_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._jobs: list[dict] = []
        self._worker:    InstallWorker | None = None
        self._thread:    QThread       | None = None
        self._completed: int           = 0
        self._install_total: int       = 0
        self._log_history: list[tuple[str, str | None]] = []
        self._build_ui()
        theme.changed.connect(self._apply_theme)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        title = QLabel("Install packages")
        title.setObjectName("sectionLabel")
        root.addWidget(title)

        hdr = QLabel("Drag & drop APK files here, or use the Add button.")
        hdr.setObjectName("mutedLabel")
        root.addWidget(hdr)

        sup = QLabel(f"Supported: {', '.join(SUPPORTED)}")
        sup.setObjectName("smallLabel")
        root.addWidget(sup)

        self._list = DropList()
        self._list.files_dropped.connect(self._add_paths)
        self._list.setMinimumHeight(160)
        root.addWidget(self._list)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("➕  Add Files…")
        add_btn.clicked.connect(self._browse)
        btn_row.addWidget(add_btn)
        remove_btn = QPushButton("✕  Remove Selected")
        remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(remove_btn)
        clear_btn = QPushButton("🗑  Clear All")
        clear_btn.clicked.connect(self._clear)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        opt_box = QGroupBox("Install Options")
        opt_l = QHBoxLayout(opt_box)
        self._reinstall_chk = QCheckBox("-r  Reinstall (keep data)")
        self._reinstall_chk.setToolTip("adb install -r: reinstall, keeping user data")
        opt_l.addWidget(self._reinstall_chk)
        self._downgrade_chk = QCheckBox("-d  Allow downgrade")
        self._downgrade_chk.setToolTip("adb install -d: allow installing older version")
        opt_l.addWidget(self._downgrade_chk)
        opt_l.addStretch()
        root.addWidget(opt_box)

        self._install_btn = QPushButton("⚡  Install All")
        self._install_btn.setObjectName("primaryButton")
        self._install_btn.clicked.connect(self._install_all)
        root.addWidget(self._install_btn)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setMaximumHeight(6)
        root.addWidget(self._progress)

        self._log = QTextEdit()
        self._log.setObjectName("logView")
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(140)
        self._log.document().setMaximumBlockCount(500)
        self._log.setFont(mono_font(10))
        root.addWidget(self._log)

    def _browse(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select APK / Bundle files", "",
            "APK & Bundles (*.apk *.xapk *.apkm *.apks *.apkx);;"
            "All files (*)"
        )
        self._add_paths(paths)

    def _add_paths(self, paths: list[str]):
        existing = {j["path"] for j in self._jobs}
        for path in paths:
            if path in existing:
                continue
            ext   = Path(path).suffix.lower()
            label = Path(path).name
            if ext not in SUPPORTED:
                self._log_line(f"Skipped (unsupported): {label}", error=True)
                continue
            self._jobs.append({"label": label, "path": path, "type": ext})
            existing.add(path)
            item = QListWidgetItem(f"{self._type_icon(ext)}  {label}")
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self._list.addItem(item)

    def _remove_selected(self):
        for item in self._list.selectedItems():
            path = item.data(Qt.ItemDataRole.UserRole)
            self._jobs = [j for j in self._jobs if j["path"] != path]
            self._list.takeItem(self._list.row(item))

    def _clear(self):
        self._jobs.clear()
        self._list.clear()

    def _type_icon(self, ext: str) -> str:
        return {
            ".apk":  "📦",
            ".xapk": "📦🔗",
            ".apkm": "📦🔗",
            ".apks": "📦🔗",
            ".apkx": "📦🔗",
        }.get(ext, "📄")

    def _install_all(self):
        if not self._jobs:
            self._log_line("No files queued.", error=True)
            return
        if not adb.is_connected():
            self._log_line("No device connected.", error=True)
            return
        if self._thread and self._thread.isRunning():
            return

        self._install_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._install_total = len(self._jobs)
        self._progress.setRange(0, self._install_total)
        self._progress.setValue(0)
        self._log.clear()
        self._log_history.clear()
        self._completed = 0

        self._worker = InstallWorker(
            jobs=list(self._jobs),
            reinstall=self._reinstall_chk.isChecked(),
            downgrade=self._downgrade_chk.isChecked(),
        )
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.done.connect(self._check_all_done)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def _on_progress(self, label: str, status: str):
        self._log_line(f"→ {status}")

    def _on_done(self, label: str, ok: bool, msg: str):
        self._completed += 1
        self._progress.setValue(self._completed)
        icon  = "✓" if ok else "✗"
        tone  = "success" if ok else "danger"
        self._log_line(f"{icon} {label}: {msg}", tone=tone)
        self.log_message.emit(f"Install {label}: {'OK' if ok else msg}")

        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and Path(item.data(Qt.ItemDataRole.UserRole)).name == label:
                item.setData(Qt.ItemDataRole.UserRole + 1, tone)
                item.setForeground(theme.qcolor(tone))

    def _check_all_done(self):
        if self._completed >= self._install_total:
            self._install_btn.setEnabled(True)
            self._progress.setVisible(False)
            self._log_line(f"Done. {self._completed} file(s) processed.")
            if self._thread:
                self._thread.quit()

    def _log_line(self, text: str, error: bool = False, tone: str | None = None):
        tone = tone or ("danger" if error else None)
        self._log_history.append((text, tone))
        if len(self._log_history) > 500:
            del self._log_history[:len(self._log_history) - 500]
        self._write_log_line(text, tone)

    def _write_log_line(self, text: str, tone: str | None, scroll: bool = True):
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(theme.qcolor(tone or "text"))
        cursor.insertText(text + "\n", fmt)
        self._log.setTextCursor(cursor)
        if scroll:
            self._log.ensureCursorVisible()

    def _apply_theme(self, _name: str = ""):
        self._log.setUpdatesEnabled(False)
        self._log.clear()
        for text, tone in self._log_history:
            self._write_log_line(text, tone, scroll=False)
        self._log.setUpdatesEnabled(True)
        self._log.ensureCursorVisible()
        for i in range(self._list.count()):
            item = self._list.item(i)
            tone = item.data(Qt.ItemDataRole.UserRole + 1)
            if tone:
                item.setForeground(theme.qcolor(tone))
