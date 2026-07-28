import webbrowser
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QMessageBox, QProgressBar, QMenu, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QPoint
from PyQt6.QtGui import QColor

from core import adb, package_db


class PackageLoader(QObject):
    progress = pyqtSignal(int)
    done     = pyqtSignal(list)

    def __init__(self, include_system: bool):
        super().__init__()
        self.include_system = include_system

    def run(self):
        try:
            pkgs  = adb.list_packages(self.include_system)
            names = package_db.lookup_all(pkgs)
            result = []
            total = max(len(pkgs), 1)
            for i, pkg in enumerate(pkgs):
                result.append({"package": pkg, "name": names.get(pkg)})
                if i % 50 == 0:
                    self.progress.emit(int(i / total * 100))
            self.progress.emit(100)
            self.done.emit(result)
        except Exception:
            self.done.emit([])


class DbCollectWorker(QObject):
    status = pyqtSignal(str)
    done   = pyqtSignal(bool, str)

    def run(self):
        try:
            ok, msg = package_db.collect(on_progress=lambda m: self.status.emit(m))
            self.done.emit(ok, msg)
        except Exception as e:
            self.done.emit(False, str(e))


class DeviceHarvestWorker(QObject):
    status = pyqtSignal(str)
    done   = pyqtSignal(int, str)

    def run(self):
        try:
            added, msg = package_db.harvest_from_device(
                on_progress=lambda m: self.status.emit(m)
            )
            self.done.emit(added, msg)
        except Exception as e:
            self.done.emit(0, str(e))


COL_NAME   = 0
COL_PKG    = 1
COL_STATUS = 2


class PackagesTab(QWidget):
    log_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_rows: list[dict] = []
        self._pkg_thread:     QThread              | None = None
        self._pkg_worker:     PackageLoader        | None = None
        self._db_thread:      QThread              | None = None
        self._db_worker:      DbCollectWorker      | None = None
        self._harvest_thread: QThread              | None = None
        self._harvest_worker: DeviceHarvestWorker  | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        bar = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search package or name…")
        self._search.textChanged.connect(self._filter)
        bar.addWidget(self._search, stretch=3)

        self._sys_check = QCheckBox("Include system packages")
        self._sys_check.setChecked(True)
        bar.addWidget(self._sys_check)

        self._refresh_btn = QPushButton("↻  Refresh")
        self._refresh_btn.clicked.connect(self.refresh)
        bar.addWidget(self._refresh_btn)

        self._update_db_btn = QPushButton("⬇  Update Name DB")
        self._update_db_btn.setToolTip("Download 5,900+ package names from the internet (once).")
        self._update_db_btn.clicked.connect(self._update_db)
        bar.addWidget(self._update_db_btn)

        self._harvest_btn = QPushButton("📱  Names from Device")
        self._harvest_btn.setToolTip("Pull app labels directly from the connected device and save to DB.")
        self._harvest_btn.clicked.connect(self._harvest_device)
        bar.addWidget(self._harvest_btn)
        root.addLayout(bar)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setMaximumHeight(6)
        root.addWidget(self._progress)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["App Name", "Package", "Status"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._context_menu)
        root.addWidget(self._table)

        row1 = QHBoxLayout()
        row1_lbl = QLabel("No root needed:")
        row1_lbl.setStyleSheet("color:#a6adc8; font-size:11px;")
        row1.addWidget(row1_lbl)

        self._user_uninstall_btn = QPushButton("🗑  Remove for User")
        self._user_uninstall_btn.setToolTip(
            "pm uninstall -k --user 0\n"
            "Removes app for current user only. Reversible. Works on most bloat."
        )
        self._user_uninstall_btn.clicked.connect(self._user_uninstall)
        row1.addWidget(self._user_uninstall_btn)

        self._reinstall_btn = QPushButton("↩  Restore for User")
        self._reinstall_btn.setToolTip("pm install-existing --user 0\nRestores a user-uninstalled package.")
        self._reinstall_btn.clicked.connect(self._reinstall)
        row1.addWidget(self._reinstall_btn)

        self._disable_btn = QPushButton("⊘  Disable")
        self._disable_btn.setToolTip("pm disable-user --user 0\nTries without root, falls back to root if available.")
        self._disable_btn.clicked.connect(self._disable)
        row1.addWidget(self._disable_btn)

        self._enable_btn = QPushButton("✓  Enable")
        self._enable_btn.clicked.connect(self._enable)
        row1.addWidget(self._enable_btn)

        self._suspend_btn = QPushButton("⏸  Suspend")
        self._suspend_btn.setToolTip("pm suspend --user 0\nApp can't run but stays installed. No root needed.")
        self._suspend_btn.clicked.connect(self._suspend)
        row1.addWidget(self._suspend_btn)

        self._unsuspend_btn = QPushButton("▶  Unsuspend")
        self._unsuspend_btn.clicked.connect(self._unsuspend)
        row1.addWidget(self._unsuspend_btn)

        root.addLayout(row1)

        row2 = QHBoxLayout()
        row2_lbl = QLabel("Root / other:")
        row2_lbl.setStyleSheet("color:#a6adc8; font-size:11px;")
        row2.addWidget(row2_lbl)

        self._uninstall_btn = QPushButton("🗑  Uninstall (root)")
        self._uninstall_btn.setToolTip("Full uninstall via pm uninstall. Needs root for system apps.")
        self._uninstall_btn.clicked.connect(self._uninstall)
        row2.addWidget(self._uninstall_btn)

        self._stop_btn = QPushButton("■  Force Stop")
        self._stop_btn.clicked.connect(self._force_stop)
        row2.addWidget(self._stop_btn)

        self._search_web_btn = QPushButton("🔍  Search Online")
        self._search_web_btn.clicked.connect(self._search_online)
        row2.addWidget(self._search_web_btn)

        row2.addStretch()
        root.addLayout(row2)

        self._status = QLabel("Not loaded. Click Refresh.")
        root.addWidget(self._status)

    def refresh(self):
        if not adb.is_connected():
            self._status.setText("No device connected.")
            return
        if self._pkg_thread and self._pkg_thread.isRunning():
            self._pkg_thread.quit()
            self._pkg_thread.wait(2000)

        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._refresh_btn.setEnabled(False)
        self._table.setRowCount(0)
        self._all_rows.clear()

        self._pkg_worker = PackageLoader(include_system=self._sys_check.isChecked())
        self._pkg_thread = QThread()
        self._pkg_worker.moveToThread(self._pkg_thread)
        self._pkg_worker.progress.connect(self._progress.setValue)
        self._pkg_worker.done.connect(self._on_loaded)
        self._pkg_worker.done.connect(self._pkg_thread.quit)
        self._pkg_thread.started.connect(self._pkg_worker.run)
        self._pkg_thread.start()

    def _on_loaded(self, rows: list[dict]):
        self._all_rows = rows
        self._render(rows)
        self._progress.setVisible(False)
        self._refresh_btn.setEnabled(True)
        self._status.setText(
            f"{len(rows)} packages  |  DB: {package_db.db_size():,} known names"
        )

    def _render(self, rows: list[dict]):
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            pkg  = row["package"]
            name = row.get("name")
            name_cell = QTableWidgetItem(name if name else f"[{pkg}]")
            if not name:
                name_cell.setForeground(QColor("#888888"))
            self._table.setItem(i, COL_NAME, name_cell)
            pkg_item = QTableWidgetItem(pkg)
            pkg_item.setData(Qt.ItemDataRole.UserRole, pkg)
            self._table.setItem(i, COL_PKG, pkg_item)
            self._table.setItem(i, COL_STATUS, QTableWidgetItem(""))
        self._table.setSortingEnabled(True)

    def _filter(self, text: str):
        text = text.lower()
        filtered = [
            r for r in self._all_rows
            if text in r["package"].lower()
            or (r.get("name") and text in r["name"].lower())
        ]
        self._render(filtered)

    def _selected_packages(self) -> list[str]:
        rows = set(idx.row() for idx in self._table.selectedIndexes())
        return [
            self._table.item(r, COL_PKG).text()
            for r in rows if self._table.item(r, COL_PKG)
        ]

    def _set_row_status(self, pkg: str, status: str, color: str = ""):
        for r in range(self._table.rowCount()):
            item = self._table.item(r, COL_PKG)
            if item and item.text() == pkg:
                s = QTableWidgetItem(status)
                if color:
                    s.setForeground(QColor(color))
                self._table.setItem(r, COL_STATUS, s)
                break

    def _handle_result(self, pkg: str, ok: bool, out: str, ok_label: str, fail_label: str = "✗ Failed"):
        if not ok and "root not available" in out.lower():
            self._set_row_status(pkg, "✗ No root", "#cc4444")
            self.log_message.emit(f"{pkg}: needs root")
        else:
            label = ok_label if ok else f"{fail_label}: {out[:35]}"
            color = "#44bb44" if ok else "#cc4444"
            self._set_row_status(pkg, label, color)
            self.log_message.emit(f"{pkg}: {out.strip()}")

    def _user_uninstall(self):
        pkgs = self._selected_packages()
        if not pkgs:
            return
        if QMessageBox.question(
            self, "Remove for User",
            f"Remove {len(pkgs)} package(s) for current user?\n\n"
            + "\n".join(pkgs[:10])
            + (f"\n...and {len(pkgs)-10} more" if len(pkgs) > 10 else "")
            + "\n\nThis is reversible via 'Restore for User'."
        ) != QMessageBox.StandardButton.Yes:
            return
        for pkg in pkgs:
            ok, out = adb.uninstall_for_user(pkg)
            self._handle_result(pkg, ok, out, "✓ Removed (user)")

    def _reinstall(self):
        for pkg in self._selected_packages():
            ok, out = adb.reinstall_for_user(pkg)
            self._handle_result(pkg, ok, out, "✓ Restored")

    def _uninstall(self):
        pkgs = self._selected_packages()
        if not pkgs:
            return
        if QMessageBox.question(
            self, "Confirm Uninstall",
            f"Fully uninstall {len(pkgs)} package(s)?\n\n" + "\n".join(pkgs[:10])
        ) != QMessageBox.StandardButton.Yes:
            return
        for pkg in pkgs:
            ok, out = adb.uninstall_package(pkg)
            self._handle_result(pkg, ok, out, "✓ Uninstalled")

    def _disable(self):
        for pkg in self._selected_packages():
            ok, out = adb.disable_package(pkg)
            self._handle_result(pkg, ok, out, "⊘ Disabled")

    def _enable(self):
        for pkg in self._selected_packages():
            ok, out = adb.enable_package(pkg)
            self._handle_result(pkg, ok, out, "✓ Enabled")

    def _suspend(self):
        for pkg in self._selected_packages():
            ok, out = adb.suspend_package(pkg)
            self._handle_result(pkg, ok, out, "⏸ Suspended")

    def _unsuspend(self):
        for pkg in self._selected_packages():
            ok, out = adb.unsuspend_package(pkg)
            self._handle_result(pkg, ok, out, "▶ Unsuspended")

    def _force_stop(self):
        for pkg in self._selected_packages():
            ok, out = adb.force_stop(pkg)
            self._handle_result(pkg, ok, out, "■ Stopped")

    def _search_online(self):
        for pkg in self._selected_packages():
            webbrowser.open(f"https://www.apkmirror.com/?s={pkg}")

    def _search_google(self):
        for pkg in self._selected_packages():
            webbrowser.open(f"https://google.com/search?q={pkg}+android+package")

    def _context_menu(self, pos: QPoint):
        if not self._selected_packages():
            return
        menu = QMenu(self)
        menu.addAction("Remove for User (no root)").triggered.connect(self._user_uninstall)
        menu.addAction("Restore for User").triggered.connect(self._reinstall)
        menu.addSeparator()
        menu.addAction("Disable").triggered.connect(self._disable)
        menu.addAction("Enable").triggered.connect(self._enable)
        menu.addAction("Suspend").triggered.connect(self._suspend)
        menu.addAction("Unsuspend").triggered.connect(self._unsuspend)
        menu.addSeparator()
        menu.addAction("Uninstall (root)").triggered.connect(self._uninstall)
        menu.addAction("Force Stop").triggered.connect(self._force_stop)
        menu.addSeparator()
        menu.addAction("Search on APKMirror").triggered.connect(self._search_online)
        menu.addAction("Search on Google").triggered.connect(self._search_google)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _update_db(self):
        if QMessageBox.question(
            self, "Update Package Name DB",
            "Download package→name mappings from the internet\n"
            "and save locally. Only needs to be done once.\n\nContinue?"
        ) != QMessageBox.StandardButton.Yes:
            return
        if self._db_thread and self._db_thread.isRunning():
            return

        self._status.setText("Downloading package name database…")
        self._update_db_btn.setEnabled(False)

        self._db_worker = DbCollectWorker()
        self._db_thread = QThread()
        self._db_worker.moveToThread(self._db_thread)
        self._db_worker.status.connect(self._status.setText)
        self._db_worker.done.connect(self._on_db_done)
        self._db_worker.done.connect(self._db_thread.quit)
        self._db_thread.started.connect(self._db_worker.run)
        self._db_thread.start()

    def _on_db_done(self, ok: bool, msg: str):
        self._status.setText(msg)
        self._update_db_btn.setEnabled(True)

    def _harvest_device(self):
        if not adb.is_connected():
            self._status.setText("No device connected.")
            return
        if self._harvest_thread and self._harvest_thread.isRunning():
            return

        self._status.setText("Harvesting labels from device…")
        self._harvest_btn.setEnabled(False)

        self._harvest_worker = DeviceHarvestWorker()
        self._harvest_thread = QThread()
        self._harvest_worker.moveToThread(self._harvest_thread)
        self._harvest_worker.status.connect(self._status.setText)
        self._harvest_worker.done.connect(self._on_harvest_done)
        self._harvest_worker.done.connect(self._harvest_thread.quit)
        self._harvest_thread.started.connect(self._harvest_worker.run)
        self._harvest_thread.start()

    def _on_harvest_done(self, added: int, msg: str):
        self._status.setText(msg)
        self._harvest_btn.setEnabled(True)
        if added > 0 and self._all_rows:
            names = package_db.lookup_all([r["package"] for r in self._all_rows])
            for row in self._all_rows:
                row["name"] = names.get(row["package"])
            self._filter(self._search.text())
