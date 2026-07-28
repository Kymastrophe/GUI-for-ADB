import re as _re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QTextEdit, QCheckBox, QSplitter,
    QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QFont, QColor, QTextCursor, QKeyEvent

from core import adb

_ANSI_RE = _re.compile(r'\x1b\[[0-9;]*m')


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text)


class ShellRunner(QObject):
    output   = pyqtSignal(str, str)
    finished = pyqtSignal(int)

    def __init__(self, cmd: str, use_root: bool):
        super().__init__()
        self.cmd      = cmd
        self.use_root = use_root

    def run(self):
        try:
            if self.use_root:
                stdout, stderr, rc = adb.su_shell(self.cmd)
            else:
                stdout, stderr, rc = adb.shell(self.cmd)
            if stdout:
                self.output.emit(stdout, "stdout")
            if stderr:
                self.output.emit(stderr, "stderr")
            self.finished.emit(rc)
        except Exception as e:
            self.output.emit(str(e), "stderr")
            self.finished.emit(1)


class HistoryLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: list[str] = []
        self._pos: int = 0

    def push(self, cmd: str):
        if cmd and (not self._history or self._history[-1] != cmd):
            self._history.append(cmd)
        self._pos = len(self._history)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Up:
            if self._history and self._pos > 0:
                self._pos -= 1
                self.setText(self._history[self._pos])
            return
        if event.key() == Qt.Key.Key_Down:
            if self._pos < len(self._history) - 1:
                self._pos += 1
                self.setText(self._history[self._pos])
            elif self._pos >= len(self._history) - 1:
                self._pos = len(self._history)
                self.clear()
            return
        super().keyPressEvent(event)


class TerminalTab(QWidget):
    log_message = pyqtSignal(str)

    COLORS = {
        "stdout": "#e8e8e8",
        "stderr": "#ff7777",
        "info":   "#88ccff",
        "cmd":    "#88ff88",
        "rc_ok":  "#44bb44",
        "rc_err": "#ff5555",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._shell_threads: list[QThread]     = []
        self._shell_workers: list[ShellRunner] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        self._output = QTextEdit()
        self._output.setReadOnly(True)
        mono = QFont("Courier New", 10)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._output.setFont(mono)
        self._output.setStyleSheet("background:#1a1a1a; color:#e8e8e8;")
        ll.addWidget(self._output)

        cmd_row = QHBoxLayout()
        self._root_check = QCheckBox("su (root)")
        cmd_row.addWidget(self._root_check)

        self._prompt_label = QLabel("$")
        self._prompt_label.setFont(mono)
        cmd_row.addWidget(self._prompt_label)

        self._input = HistoryLineEdit()
        self._input.setFont(mono)
        self._input.setStyleSheet("background:#111; color:#e8e8e8; border:1px solid #444;")
        self._input.setPlaceholderText("Enter adb shell command…")
        self._input.returnPressed.connect(self._run_cmd)
        cmd_row.addWidget(self._input, stretch=1)

        run_btn = QPushButton("Run")
        run_btn.clicked.connect(self._run_cmd)
        cmd_row.addWidget(run_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._output.clear)
        cmd_row.addWidget(clear_btn)

        ll.addLayout(cmd_row)
        splitter.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)
        rl.addWidget(QLabel("Quick Commands"))

        self._quick_list = QListWidget()
        self._quick_list.itemDoubleClicked.connect(self._quick_run)
        rl.addWidget(self._quick_list)

        for cmd in [
            "id", "whoami", "uname -a",
            "getprop ro.product.model",
            "getprop ro.build.version.release",
            "df -h", "free -m",
            "cat /proc/cpuinfo | head -20",
            "ip addr", "netstat -tuln",
            "ls /sdcard", "ls /data/data",
            "logcat -d -t 100",
            "dumpsys battery", "dumpsys wifi",
            "settings list global",
            "wm size", "wm density",
        ]:
            self._quick_list.addItem(QListWidgetItem(cmd))

        add_row = QHBoxLayout()
        self._custom_quick = QLineEdit()
        self._custom_quick.setPlaceholderText("Add quick command…")
        add_row.addWidget(self._custom_quick)
        add_btn = QPushButton("+")
        add_btn.setMaximumWidth(30)
        add_btn.clicked.connect(self._add_quick)
        add_row.addWidget(add_btn)
        rl.addLayout(add_row)

        splitter.addWidget(right)
        splitter.setSizes([700, 200])

        reboot_row = QHBoxLayout()
        reboot_row.addWidget(QLabel("Reboot:"))
        for label, mode in [("System", ""), ("Recovery", "recovery"),
                             ("Bootloader", "bootloader"), ("Fastboot", "fastboot")]:
            btn = QPushButton(label)
            btn.clicked.connect(self._make_reboot_fn(mode))
            reboot_row.addWidget(btn)
        reboot_row.addStretch()
        root.addLayout(reboot_row)

    def _make_reboot_fn(self, mode: str):
        def fn():
            ok, msg = adb.reboot(mode)
            self._append(f"Reboot {mode or 'system'}: {msg}", "info" if ok else "stderr")
        return fn

    def _run_cmd(self):
        cmd = self._input.text().strip()
        if not cmd:
            return
        if not adb.is_connected():
            self._append("No device connected.", "stderr")
            return
        self._input.push(cmd)
        self._input.clear()
        use_root = self._root_check.isChecked()
        self._append(f"{'#' if use_root else '$'} {cmd}", "cmd")
        self._prompt_label.setText("#" if use_root else "$")

        runner = ShellRunner(cmd, use_root=use_root)
        thread = QThread()
        runner.moveToThread(thread)
        runner.output.connect(self._append)
        runner.finished.connect(self._on_cmd_finished)
        runner.finished.connect(thread.quit)
        thread.finished.connect(self._cleanup_threads)
        thread.started.connect(runner.run)

        self._shell_workers.append(runner)
        self._shell_threads.append(thread)
        thread.start()

    def _cleanup_threads(self):
        alive_threads  = [t for t in self._shell_threads if t.isRunning()]
        alive_workers  = [w for t, w in zip(self._shell_threads, self._shell_workers) if t.isRunning()]
        self._shell_threads = alive_threads
        self._shell_workers = alive_workers

    def _on_cmd_finished(self, rc: int):
        self._append(f"[exit {rc}]", "rc_ok" if rc == 0 else "rc_err")

    def _quick_run(self, item: QListWidgetItem):
        self._input.setText(item.text())
        self._run_cmd()

    def _add_quick(self):
        cmd = self._custom_quick.text().strip()
        if cmd:
            self._quick_list.addItem(QListWidgetItem(cmd))
            self._custom_quick.clear()

    def _append(self, text: str, kind: str = "stdout"):
        text  = strip_ansi(text)
        color = self.COLORS.get(kind, "#e8e8e8")
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = cursor.charFormat()
        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)
        cursor.insertText(text.rstrip("\n") + "\n")
        self._output.setTextCursor(cursor)
        self._output.ensureCursorVisible()
