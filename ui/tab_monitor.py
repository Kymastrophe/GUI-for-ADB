from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QAbstractItemView, QSpinBox, QLineEdit, QMenu, QFrame,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject, QPoint
from PyQt6.QtGui import QColor, QFont

from core import adb


class MonitorLoader(QObject):
    done = pyqtSignal(dict, list)

    def __init__(self):
        super().__init__()
        self._prev: dict | None = None

    def run(self):
        try:
            result     = adb.get_monitor_snapshot(self._prev)
            self._prev = result["raw_proc_stats"]
            self.done.emit(result["stats"], result["procs"])
        except Exception:
            self.done.emit({}, [])


COL_PID    = 0
COL_NAME   = 1
COL_USER   = 2
COL_MEM_MB = 3
COL_MEM_PC = 4
COL_STATE  = 5


def _pct_color(pct: float) -> str:
    if pct < 50: return "#a6e3a1"
    if pct < 75: return "#f9e2af"
    return "#f38ba8"

_STATE_COLORS = {
    "R": "#a6e3a1",
    "S": "#cdd6f4",
    "D": "#f9e2af",
    "Z": "#f38ba8",
    "T": "#89b4fa",
}


class NumericItem(QTableWidgetItem):
    def __init__(self, display: str, sort_key: float):
        super().__init__(display)
        self._k = sort_key

    def __lt__(self, other):
        return self._k < other._k if isinstance(other, NumericItem) else super().__lt__(other)


class StatCard(QFrame):
    def __init__(self, title: str, accent: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet("QFrame{background:#181825;border:1px solid #313244;border-radius:6px;}")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)

        lbl = QLabel(title)
        lbl.setStyleSheet("color:#585b70;font-size:10px;border:none;")
        lay.addWidget(lbl)

        self._val = QLabel("—")
        f = QFont()
        f.setBold(True)
        f.setPointSize(14)
        self._val.setFont(f)
        self._val.setStyleSheet(f"color:{accent};border:none;")
        lay.addWidget(self._val)

        self._sub = QLabel("")
        self._sub.setStyleSheet("color:#6c7086;font-size:10px;border:none;")
        self._sub.setVisible(False)
        lay.addWidget(self._sub)

        self._accent = accent

    def update(self, value: str, sub: str = "", color: str = ""):
        self._val.setText(value)
        self._val.setStyleSheet(f"color:{color or self._accent};border:none;")
        self._sub.setText(sub)
        self._sub.setVisible(bool(sub))


class MonitorTab(QWidget):
    log_message = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._procs:  list[dict] = []
        self._timer   = QTimer(self)
        self._timer.timeout.connect(self._load)
        self._thread: QThread       | None = None
        self._worker: MonitorLoader | None = None
        self._loading = False
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(8)
        self._c_ram_used  = StatCard("RAM Used",  "#89b4fa")
        self._c_ram_pct   = StatCard("RAM %",     "#cba6f7")
        self._c_ram_total = StatCard("Total RAM", "#6c7086")
        self._c_cpu       = StatCard("CPU %",     "#a6e3a1")
        self._c_procs     = StatCard("Processes", "#89dceb")
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
        bar.addWidget(self._interval)

        self._refresh_btn = QPushButton("↻  Refresh Now")
        self._refresh_btn.clicked.connect(self._load)
        bar.addWidget(self._refresh_btn)
        root.addLayout(bar)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["PID", "Process", "User", "Mem (MB)", "Mem %", "State"]
        )
        h = self._table.horizontalHeader()
        for col in (COL_PID, COL_USER, COL_MEM_MB, COL_MEM_PC, COL_STATE):
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
        self._count_lbl.setStyleSheet("color:#6c7086;")
        act.addWidget(self._count_lbl)
        root.addLayout(act)

    def _load(self):
        if not adb.is_connected() or self._loading:
            return
        self._loading = True
        self._refresh_btn.setEnabled(False)
        if self._worker is None:
            self._worker = MonitorLoader()
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._worker.done.connect(self._on_loaded)
        self._worker.done.connect(self._thread.quit)
        self._thread.started.connect(self._worker.run)
        self._thread.finished.connect(self._on_thread_done)
        self._thread.start()

    def _on_thread_done(self):
        self._loading = False
        self._refresh_btn.setEnabled(True)

    def _on_loaded(self, stats: dict, procs: list[dict]):
        self._procs = procs
        self._update_summary(stats, len(procs))
        self._apply_filter(self._search.text())

    def _update_summary(self, s: dict, n: int):
        if not s:
            return
        total_mb = s.get("total_ram_kb", 0) / 1024
        used_mb  = s.get("used_ram_kb",  0) / 1024
        mp       = s.get("mem_pct", 0.0)
        cp       = s.get("cpu_pct", 0.0)

        self._c_ram_used.update(f"{used_mb:.0f} MB", f"of {total_mb:.0f} MB", _pct_color(mp))
        self._c_ram_pct.update(f"{mp:.1f}%", color=_pct_color(mp))
        self._c_ram_total.update(
            f"{total_mb/1024:.1f} GB" if total_mb >= 1024 else f"{total_mb:.0f} MB"
        )
        self._c_cpu.update(f"{cp:.1f}%", color=_pct_color(cp))
        self._c_procs.update(str(n))

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

    def _render(self, procs: list[dict]):
        tbl = self._table
        tbl.setSortingEnabled(False)
        tbl.setUpdatesEnabled(False)
        tbl.setRowCount(len(procs))

        for i, p in enumerate(procs):
            mem_mb  = p.get("mem_mb",  0.0)
            mem_pct = p.get("mem_pct", 0.0)
            state   = p.get("state",  "?")
            color   = _pct_color(mem_pct)

            tbl.setItem(i, COL_PID, NumericItem(p.get("pid", ""), float(p.get("pid", 0) or 0)))

            name = p.get("name", "")
            ni = QTableWidgetItem(name)
            if ":" in name:
                ni.setForeground(QColor("#89b4fa"))
            tbl.setItem(i, COL_NAME, ni)

            tbl.setItem(i, COL_USER, QTableWidgetItem(p.get("user", "")))

            mb = NumericItem(f"{mem_mb:.1f}", mem_mb)
            mb.setForeground(QColor(color))
            mb.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tbl.setItem(i, COL_MEM_MB, mb)

            pc = NumericItem(f"{mem_pct:.2f}%", mem_pct)
            pc.setForeground(QColor(color))
            pc.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tbl.setItem(i, COL_MEM_PC, pc)

            st = QTableWidgetItem(state)
            st.setForeground(QColor(_STATE_COLORS.get(state, "#a6adc8")))
            st.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            tbl.setItem(i, COL_STATE, st)

        tbl.setUpdatesEnabled(True)
        tbl.setSortingEnabled(True)
        self._count_lbl.setText(f"{len(procs)} processes")

        if procs and tbl.columnWidth(COL_NAME) < 180:
            tbl.setColumnWidth(COL_NAME, 260)

    def _toggle_auto(self, on: bool):
        if on:
            self._timer.start(self._interval.value() * 1000)
            self._load()
        else:
            self._timer.stop()

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
        if not self._selected_pids():
            return
        m = QMenu(self)
        m.addAction("Kill").triggered.connect(self._kill_normal)
        m.addAction("Kill (root)").triggered.connect(self._kill_root)
        m.exec(self._table.viewport().mapToGlobal(pos))

    def showEvent(self, e):
        super().showEvent(e)
        self._load()
