from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QAbstractItemView, QSpinBox, QLineEdit, QMenu, QFrame,
    QSizePolicy,
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, pyqtSlot, QObject, QPoint,
    QItemSelectionModel,
)
from PyQt6.QtGui import QFont

from core import adb
from ui.theme import theme


class MonitorLoader(QObject):
    done = pyqtSignal(dict, list)

    def __init__(self):
        super().__init__()
        # Kept in this worker so the CPU delta survives between refreshes.
        self._prev: dict | None = None

    @pyqtSlot()
    def run(self):
        try:
            if not adb.is_connected():
                self.done.emit({}, [])
                return
            result = adb.get_monitor_snapshot(self._prev)
            self._prev = result["raw_proc_stats"]
            self.done.emit(result["stats"], result["procs"])
        except Exception:
            self.done.emit({}, [])


COL_PID    = 0
COL_NAME   = 1
COL_USER   = 2
COL_MEM_MB = 3
COL_MEM_PC = 4
COL_CPU    = 5
COL_STATE  = 6


def _pct_tone(pct: float) -> str:
    if pct < 50:
        return "success"
    if pct < 75:
        return "warning"
    return "danger"

_STATE_TONES = {
    "R": "success",
    "S": "text",
    "D": "warning",
    "Z": "danger",
    "T": "info",
}


class NumericItem(QTableWidgetItem):
    def __init__(self, display: str, sort_key: float):
        super().__init__(display)
        self._k = sort_key

    def __lt__(self, other):
        return self._k < other._k if isinstance(other, NumericItem) else super().__lt__(other)


class StatCard(QFrame):
    def __init__(self, title: str, accent_key: str, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)

        lbl = QLabel(title)
        lbl.setObjectName("statLabel")
        lay.addWidget(lbl)

        self._val = QLabel("—")
        f = QFont()
        f.setBold(True)
        f.setPointSize(14)
        self._val.setFont(f)
        lay.addWidget(self._val)

        self._sub = QLabel("")
        self._sub.setObjectName("statSub")
        self._sub.setVisible(False)
        lay.addWidget(self._sub)

        self._accent_key = accent_key
        self._accent = theme.color(accent_key)
        self._last_value = "—"
        self._last_sub = ""
        self._last_tone: str | None = None
        self._render()

    def _render(self):
        color = theme.color(self._last_tone) if self._last_tone else self._accent
        self._val.setText(self._last_value)
        self._val.setStyleSheet(f"color:{color};border:none;")
        self._sub.setText(self._last_sub)
        self._sub.setVisible(bool(self._last_sub))

    def set_value(self, value: str, sub: str = "", tone: str | None = None):
        self._last_value = value
        self._last_sub = sub
        self._last_tone = tone
        self._render()

    def apply_theme(self):
        self._accent = theme.color(self._accent_key)
        self._render()


class MonitorTab(QWidget):
    log_message = pyqtSignal(str)
    _request_load = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._procs:  list[dict] = []
        self._last_stats: dict = {}
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._load)
        self._loading = False
        self._build_ui()
        theme.changed.connect(self._apply_theme)

        # A persistent worker thread avoids creating a QThread (and its event
        # loop) every second.  All ADB calls stay off the GUI thread.
        self._thread = QThread(self)
        self._worker = MonitorLoader()
        self._worker.moveToThread(self._thread)
        self._request_load.connect(self._worker.run)
        self._worker.done.connect(self._on_loaded)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(8)
        self._c_ram_used  = StatCard("RAM Used",  "info")
        self._c_ram_pct   = StatCard("RAM %",     "accent")
        self._c_ram_total = StatCard("Total RAM", "muted")
        self._c_cpu       = StatCard("CPU %",     "success")
        self._c_procs     = StatCard("Processes", "cyan")
        for c in (self._c_ram_used, self._c_ram_pct, self._c_ram_total,
                  self._c_cpu, self._c_procs):
            cards_row.addWidget(c)
        root.addLayout(cards_row)

        bar = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by name, PID, or user…")
        self._search.textChanged.connect(self._apply_filter)
        bar.addWidget(self._search, stretch=1)

        self._auto_chk = QCheckBox("Auto-refresh every")
        self._auto_chk.toggled.connect(self._toggle_auto)
        bar.addWidget(self._auto_chk)

        self._interval = QSpinBox()
        self._interval.setRange(1, 60)
        self._interval.setValue(3)
        self._interval.setSuffix(" s")
        self._interval.setMaximumWidth(65)
        self._interval.valueChanged.connect(self._on_interval_changed)
        bar.addWidget(self._interval)

        self._refresh_btn = QPushButton("↻  Refresh Now")
        self._refresh_btn.clicked.connect(self._load)
        bar.addWidget(self._refresh_btn)
        root.addLayout(bar)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["PID", "Process", "User", "Mem (MB)", "Mem %", "CPU %", "State"]
        )
        self._table.horizontalHeaderItem(COL_CPU).setToolTip(
            "Share of total device CPU across all cores, matching the global CPU card."
        )
        h = self._table.horizontalHeader()
        for col in (COL_PID, COL_USER, COL_MEM_MB, COL_MEM_PC, COL_CPU, COL_STATE):
            h.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Interactive)
        h.setMinimumSectionSize(80)

        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.sortByColumn(COL_MEM_MB, Qt.SortOrder.DescendingOrder)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._ctx_menu)
        root.addWidget(self._table)

        act = QHBoxLayout()
        kill_btn = QPushButton("✕  Kill Selected")
        kill_btn.clicked.connect(self._kill_normal)
        act.addWidget(kill_btn)
        kill_root_btn = QPushButton("✕  Kill (root)")
        kill_root_btn.clicked.connect(self._kill_root)
        act.addWidget(kill_root_btn)
        act.addStretch()
        self._count_lbl = QLabel("0 processes")
        self._count_lbl.setObjectName("mutedLabel")
        act.addWidget(self._count_lbl)
        root.addLayout(act)

    def _load(self):
        if self._loading or not self._thread.isRunning():
            return
        self._loading = True
        self._refresh_btn.setEnabled(False)
        self._request_load.emit()

    def _on_loaded(self, stats: dict, procs: list[dict]):
        self._loading = False
        self._refresh_btn.setEnabled(True)

        if not stats and not procs:
            self._procs = []
            self._last_stats = {}
            self._table.setRowCount(0)
            for card in (self._c_ram_used, self._c_ram_pct, self._c_ram_total,
                         self._c_cpu, self._c_procs):
                card.set_value("—")
            self._count_lbl.setText("No process data")
            return

        self._procs = procs
        self._last_stats = stats
        self._update_summary(stats, len(procs))
        self._apply_filter(self._search.text())

    def _update_summary(self, s: dict, n: int):
        if not s:
            return
        total_mb = s.get("total_ram_kb", 0) / 1024
        used_mb  = s.get("used_ram_kb",  0) / 1024
        mp       = s.get("mem_pct", 0.0)
        cp       = s.get("cpu_pct", 0.0)

        self._c_ram_used.set_value(f"{used_mb:.0f} MB", f"of {total_mb:.0f} MB", _pct_tone(mp))
        self._c_ram_pct.set_value(f"{mp:.1f}%", tone=_pct_tone(mp))
        self._c_ram_total.set_value(
            f"{total_mb/1024:.1f} GB" if total_mb >= 1024 else f"{total_mb:.0f} MB"
        )
        self._c_cpu.set_value(f"{cp:.1f}%", tone=_pct_tone(cp))
        self._c_procs.set_value(str(n))

    def _apply_filter(self, text: str = ""):
        t = text.lower()
        filtered = [
            p for p in self._procs
            if not t
            or t in p.get("name", "").lower()
            or t in p.get("pid",  "")
            or t in p.get("user", "").lower()
        ]
        self._render(filtered)

    def _apply_theme(self, _name: str = ""):
        for card in (self._c_ram_used, self._c_ram_pct, self._c_ram_total,
                     self._c_cpu, self._c_procs):
            card.apply_theme()
        if self._last_stats:
            self._update_summary(self._last_stats, len(self._procs))
        self._apply_filter(self._search.text())

    def _render(self, procs: list[dict]):
        tbl = self._table
        scroll_pos = tbl.verticalScrollBar().value()
        selected = set(self._selected_pids())

        tbl.setSortingEnabled(False)
        tbl.setUpdatesEnabled(False)
        # Clearing first is important: replacing items in an already sorted
        # QTableWidget makes every setItem() call pathologically slow on some
        # Qt builds (one refresh could block the UI for 20+ seconds).
        tbl.setRowCount(0)
        tbl.setRowCount(len(procs))

        for i, p in enumerate(procs):
            mem_mb  = p.get("mem_mb",  0.0)
            mem_pct = p.get("mem_pct", 0.0)
            state   = p.get("state",  "?")
            tone    = _pct_tone(mem_pct)

            tbl.setItem(i, COL_PID, NumericItem(p.get("pid", ""), float(p.get("pid", 0) or 0)))

            name = p.get("name", "")
            ni = QTableWidgetItem(name)
            if ":" in name:
                ni.setForeground(theme.qcolor("info"))
            tbl.setItem(i, COL_NAME, ni)

            tbl.setItem(i, COL_USER, QTableWidgetItem(p.get("user", "")))

            mb = NumericItem(f"{mem_mb:.1f}", mem_mb)
            mb.setForeground(theme.qcolor(tone))
            mb.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tbl.setItem(i, COL_MEM_MB, mb)

            pc = NumericItem(f"{mem_pct:.2f}%", mem_pct)
            pc.setForeground(theme.qcolor(tone))
            pc.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tbl.setItem(i, COL_MEM_PC, pc)

            cpu_pct = p.get("cpu_pct")
            if cpu_pct is None:
                cpu = NumericItem("—", -1.0)
                cpu.setForeground(theme.qcolor("muted"))
            else:
                cpu = NumericItem(f"{cpu_pct:.1f}%", cpu_pct)
                cpu.setForeground(theme.qcolor(_pct_tone(cpu_pct)))
            cpu.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tbl.setItem(i, COL_CPU, cpu)

            st = QTableWidgetItem(state)
            st.setForeground(theme.qcolor(_STATE_TONES.get(state, "muted")))
            st.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            tbl.setItem(i, COL_STATE, st)

        tbl.setUpdatesEnabled(True)
        tbl.setSortingEnabled(True)
        self._count_lbl.setText(f"{len(procs)} processes")

        if procs and tbl.columnWidth(COL_NAME) < 180:
            tbl.setColumnWidth(COL_NAME, 260)

        # Keep the view stable while auto-refreshing: restore the scroll
        # position and any selected process rows after the rebuild/sort.
        bar = tbl.verticalScrollBar()
        bar.setValue(min(scroll_pos, bar.maximum()))
        if selected:
            model = tbl.model()
            sel = tbl.selectionModel()
            sel.clearSelection()
            flags = (
                QItemSelectionModel.SelectionFlag.Select
                | QItemSelectionModel.SelectionFlag.Rows
            )
            for row in range(tbl.rowCount()):
                item = tbl.item(row, COL_PID)
                if item and item.text() in selected:
                    sel.select(model.index(row, 0), flags)

    def _toggle_auto(self, on: bool):
        if on:
            self._timer.start(self._interval.value() * 1000)
            self._load()
        else:
            self._timer.stop()

    def _on_interval_changed(self, seconds: int):
        if self._timer.isActive():
            self._timer.setInterval(seconds * 1000)

    def _selected_pids(self) -> list[str]:
        rows = set(idx.row() for idx in self._table.selectedIndexes())
        return [self._table.item(r, COL_PID).text()
                for r in rows if self._table.item(r, COL_PID)]

    def _kill_normal(self): self._kill(False)
    def _kill_root(self):   self._kill(True)

    def _kill(self, root: bool):
        for pid in self._selected_pids():
            ok, msg = adb.kill_process(pid, use_root=root)
            self.log_message.emit(f"Kill {pid}: {msg}")
        self._load()

    def _ctx_menu(self, pos: QPoint):
        index = self._table.indexAt(pos)
        if index.isValid() and not self._table.selectionModel().isRowSelected(
            index.row(), index.parent()
        ):
            self._table.selectRow(index.row())
        if not self._selected_pids():
            return
        m = QMenu(self)
        m.addAction("Kill").triggered.connect(self._kill_normal)
        m.addAction("Kill (root)").triggered.connect(self._kill_root)
        m.exec(self._table.viewport().mapToGlobal(pos))

    def showEvent(self, e):
        super().showEvent(e)
        if self._auto_chk.isChecked():
            self._timer.start(self._interval.value() * 1000)
        self._load()

    def hideEvent(self, e):
        self._timer.stop()
        super().hideEvent(e)

    def shutdown(self):
        self._timer.stop()
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
