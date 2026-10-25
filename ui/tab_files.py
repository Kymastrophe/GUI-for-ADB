import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QFileDialog, QMessageBox, QProgressBar, QAbstractItemView, QMenu,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QPoint, QTimer

from core import adb
from ui.theme import theme

_CHUNK = 200


class DirLoader(QObject):
    done = pyqtSignal(str, list, int)

    def __init__(self, path: str, token: int):
        super().__init__()
        self._path  = path
        self._token = token

    def run(self):
        try:
            entries = adb.list_dir(self._path)
        except Exception:
            entries = []
        self.done.emit(self._path, entries, self._token)


class TransferWorker(QObject):
    done = pyqtSignal(bool, str)

    def __init__(self, mode: str, src: str, dst: str):
        super().__init__()
        self.mode, self.src, self.dst = mode, src, dst

    def run(self):
        try:
            if self.mode == "pull":
                ok, msg = adb.pull_file(self.src, self.dst)
            elif self.mode == "push":
                ok, msg = adb.push_file(self.src, self.dst)
            elif self.mode == "delete":
                ok, msg = adb.delete_file(self.src)
            else:
                ok, msg = False, "Unknown mode"
            self.done.emit(ok, msg)
        except Exception as e:
            self.done.emit(False, str(e))


COL_NAME  = 0
COL_SIZE  = 1
COL_PERMS = 2


class FilesTab(QWidget):
    log_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path         = "/"
        self._history:     list[str] = ["/"]
        self._history_pos: int       = 0
        self._load_token:  int       = 0
        self._pending_entries: list  = []
        self._pending_path:    str   = ""
        self._chunk_offset:    int   = 0
        self._dir_thread:  QThread        | None = None
        self._dir_worker:  DirLoader      | None = None
        self._xfer_thread: QThread        | None = None
        self._xfer_worker: TransferWorker | None = None
        self._build_ui()
        theme.changed.connect(self._apply_theme)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)

        nav = QHBoxLayout()
        self._back_btn = QPushButton("◀")
        self._back_btn.setMaximumWidth(32)
        self._back_btn.clicked.connect(self._go_back)
        nav.addWidget(self._back_btn)

        up_btn = QPushButton("▲ Up")
        up_btn.clicked.connect(self._go_up)
        nav.addWidget(up_btn)

        self._path_edit = QLineEdit("/")
        self._path_edit.returnPressed.connect(self._go_to_path_edit)
        nav.addWidget(self._path_edit, stretch=1)

        go_btn = QPushButton("Go")
        go_btn.clicked.connect(self._go_to_path_edit)
        nav.addWidget(go_btn)

        ref_btn = QPushButton("Refresh")
        ref_btn.setToolTip("Reload the current directory")
        ref_btn.clicked.connect(self._reload_current)
        nav.addWidget(ref_btn)
        root.addLayout(nav)

        quick = QHBoxLayout()
        for label, path in [("/", "/"), ("/sdcard", "/sdcard"), ("/data", "/data"),
                             ("/system", "/system"), ("/proc", "/proc"), ("/sys", "/sys")]:
            btn = QPushButton(label)
            btn.setMaximumWidth(80)
            btn.clicked.connect(self._make_nav_fn(path))
            quick.addWidget(btn)
        quick.addStretch()
        root.addLayout(quick)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Name", "Size", "Permissions"])
        h = self._table.horizontalHeader()
        h.setSectionResizeMode(COL_NAME,  QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(COL_SIZE,  QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_PERMS, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(False)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._ctx_menu)
        self._table.cellDoubleClicked.connect(self._on_double_click)
        root.addWidget(self._table)

        act = QHBoxLayout()
        pull_btn = QPushButton("⬇  Pull to PC")
        pull_btn.clicked.connect(self._pull)
        act.addWidget(pull_btn)
        push_btn = QPushButton("⬆  Push from PC")
        push_btn.clicked.connect(self._push)
        act.addWidget(push_btn)
        del_btn = QPushButton("🗑  Delete")
        del_btn.clicked.connect(self._delete)
        act.addWidget(del_btn)
        act.addStretch()
        self._status = QLabel("Browse device filesystem above.")
        self._status.setObjectName("mutedLabel")
        act.addWidget(self._status)
        root.addLayout(act)

        self._progress = QProgressBar()
        self._progress.setMaximumHeight(6)
        self._progress.setVisible(False)
        root.addWidget(self._progress)

    def _make_nav_fn(self, path: str):
        def fn(): self._navigate(path)
        return fn

    def _go_to_path_edit(self):
        self._navigate(self._path_edit.text())

    def _reload_current(self):
        self._load(self._path)

    def _go_up(self):
        self._navigate(os.path.dirname(self._path) or "/")

    def _go_back(self):
        if self._history_pos > 0:
            self._history_pos -= 1
            path = self._history[self._history_pos]
            self._path = path
            self._path_edit.setText(path)
            self._load(path)

    def _navigate(self, path: str):
        path = path.strip() or "/"
        if not path.startswith("/"):
            path = self._path.rstrip("/") + "/" + path
        while "//" in path:
            path = path.replace("//", "/")
        self._path = path
        self._path_edit.setText(path)
        if self._history_pos < len(self._history) - 1:
            self._history = self._history[:self._history_pos + 1]
        self._history.append(path)
        self._history_pos = len(self._history) - 1
        self._load(path)

    def _on_double_click(self, row: int, _col: int):
        kind = self._table.item(row, COL_NAME)
        if kind and kind.data(Qt.ItemDataRole.UserRole + 1) == "dir":
            self._navigate(kind.data(Qt.ItemDataRole.UserRole))

    def _load(self, path: str):
        if not adb.is_connected():
            self._status.setText("No device connected.")
            return

        self._load_token += 1
        token = self._load_token

        self._status.setText(f"Loading {path}…")
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._table.setUpdatesEnabled(True)
        self._table.setRowCount(0)

        worker = DirLoader(path, token)
        thread = QThread(self)
        worker.moveToThread(thread)
        worker.done.connect(self._on_loaded)
        worker.done.connect(thread.quit)
        thread.started.connect(worker.run)
        self._dir_worker = worker
        self._dir_thread = thread
        thread.start()

    def _on_loaded(self, path: str, entries: list, token: int):
        if token != self._load_token:
            return

        self._progress.setVisible(False)

        dirs  = sorted([e for e in entries if  e.get("is_dir")], key=lambda e: e["name"].lower())
        files = sorted([e for e in entries if not e.get("is_dir")], key=lambda e: e["name"].lower())
        ordered = dirs + files

        if not ordered:
            self._status.setText(f"{path}  —  empty (or permission denied)")
            return

        self._status.setText(f"{path}  —  {len(ordered)} item(s)  (loading…)")
        self._pending_entries = ordered
        self._pending_path    = path
        self._chunk_offset    = 0
        self._table.setUpdatesEnabled(False)
        self._table.setRowCount(len(ordered))
        self._fill_chunk(token)

    def _fill_chunk(self, token: int):
        if token != self._load_token:
            return

        entries = self._pending_entries
        path    = self._pending_path
        start   = self._chunk_offset
        end     = min(start + _CHUNK, len(entries))

        for i in range(start, end):
            e      = entries[i]
            name   = e["name"]
            is_dir = e.get("is_dir", False)
            full   = adb._normalize_android_path(path.rstrip("/") + "/" + name)

            icon = "📁 " if is_dir else "📄 "
            name_item = QTableWidgetItem(icon + name)
            name_item.setData(Qt.ItemDataRole.UserRole, full)
            name_item.setData(Qt.ItemDataRole.UserRole + 1, "dir" if is_dir else "file")
            if is_dir:
                name_item.setForeground(theme.qcolor("info"))
            self._table.setItem(i, COL_NAME,  name_item)
            self._table.setItem(i, COL_SIZE,  QTableWidgetItem(e.get("size", "")))
            self._table.setItem(i, COL_PERMS, QTableWidgetItem(e.get("perms", "")))

        self._chunk_offset = end

        if end < len(entries):
            QTimer.singleShot(0, lambda: self._fill_chunk(token))
        else:
            self._table.setUpdatesEnabled(True)
            self._status.setText(f"{path}  —  {len(entries)} item(s)")

    def _apply_theme(self, _name: str = ""):
        for row in range(self._table.rowCount()):
            item = self._table.item(row, COL_NAME)
            if item and item.data(Qt.ItemDataRole.UserRole + 1) == "dir":
                item.setForeground(theme.qcolor("info"))

    def _selected_paths(self) -> list[str]:
        rows = set(idx.row() for idx in self._table.selectedIndexes())
        result = []
        for r in sorted(rows):
            item = self._table.item(r, COL_NAME)
            if item:
                p = item.data(Qt.ItemDataRole.UserRole)
                if p:
                    result.append(p)
        return result

    def _pull(self):
        paths = self._selected_paths()
        if not paths:
            return
        dest = QFileDialog.getExistingDirectory(self, "Select destination folder")
        if not dest:
            return
        self._run_transfer("pull", paths[0], dest)

    def _push(self):
        local, _ = QFileDialog.getOpenFileName(self, "Select file to push")
        if not local:
            return
        remote = self._path.rstrip("/") + "/" + os.path.basename(local)
        self._run_transfer("push", local, remote)

    def _delete(self):
        paths = self._selected_paths()
        if not paths:
            return
        if QMessageBox.question(
            self, "Confirm Delete",
            f"Delete {len(paths)} item(s)?\nThis cannot be undone.",
        ) != QMessageBox.StandardButton.Yes:
            return
        for p in paths:
            ok, msg = adb.delete_file(p)
            self.log_message.emit(f"Delete {p}: {'OK' if ok else msg}")
        self._load(self._path)

    def _run_transfer(self, mode: str, src: str, dst: str):
        if self._xfer_thread and self._xfer_thread.isRunning():
            return
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._xfer_worker = TransferWorker(mode, src, dst)
        self._xfer_thread = QThread(self)
        self._xfer_worker.moveToThread(self._xfer_thread)
        self._xfer_worker.done.connect(self._on_xfer_done)
        self._xfer_worker.done.connect(self._xfer_thread.quit)
        self._xfer_thread.started.connect(self._xfer_worker.run)
        self._xfer_thread.start()

    def _on_xfer_done(self, ok: bool, msg: str):
        self._status.setText(msg)
        self._progress.setVisible(False)
        self.log_message.emit(f"Transfer: {msg}")

    def _ctx_menu(self, pos: QPoint):
        index = self._table.indexAt(pos)
        if index.isValid() and not self._table.selectionModel().isRowSelected(
            index.row(), index.parent()
        ):
            self._table.selectRow(index.row())
        if not self._selected_paths():
            return
        m = QMenu(self)
        m.addAction("Pull to PC").triggered.connect(self._pull)
        m.addAction("Delete").triggered.connect(self._delete)
        m.exec(self._table.viewport().mapToGlobal(pos))

    def showEvent(self, event):
        super().showEvent(event)
        if adb.is_connected() and not self._table.rowCount():
            self._load("/")
