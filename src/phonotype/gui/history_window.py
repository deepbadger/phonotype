"""History window: search past dictations, see what was recognised next to
what was typed, copy or delete an entry."""
from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
    QVBoxLayout, QWidget,
)

from phonotype.core import history
from phonotype.gui.settings_window import _WINDOW_QSS, _hint_label, prompt_title


def entry_title(entry: dict, limit: int = 60) -> str:
    """'24.11 16:34  First words of the dictation…'"""
    try:
        when = datetime.fromisoformat(entry["ts"]).strftime("%d.%m %H:%M")
    except (KeyError, ValueError):
        when = "?"
    flat = " ".join(str(entry.get("text", "")).split())
    if len(flat) > limit:
        flat = flat[:limit - 1].rstrip() + "…"
    return f"{when}  {flat}"


def entry_details(entry: dict) -> str:
    """'24 November 2026, 16:34:58 · ggml-….bin · AI: Default'"""
    parts = []
    try:
        parts.append(datetime.fromisoformat(entry["ts"]).strftime("%d %B %Y, %H:%M:%S"))
    except (KeyError, ValueError):
        pass
    if entry.get("model"):
        parts.append(str(entry["model"]))
    if entry.get("prompt"):
        parts.append(f"AI: {prompt_title(str(entry['prompt']))}")
    return " · ".join(parts)


class HistoryWindow(QDialog):
    def __init__(self, cfg, parent: QWidget | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Phonotype History")
        self.setStyleSheet(_WINDOW_QSS + """
QListWidget#historyList { background-color: #1e1e1e; color: white; border: 1px solid #555; outline: none; }
QListWidget#historyList::item { padding: 5px 6px; }
QListWidget#historyList::item:selected { background-color: #E03D00; color: white; }
""")
        self.resize(900, 600)
        self._entries: list[dict] = []
        self._shown: list[dict] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search dictations…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _=None: self._filter())
        root.addWidget(self.search)

        split = QSplitter(Qt.Orientation.Horizontal)
        self.list = QListWidget()
        self.list.setObjectName("historyList")
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.currentRowChanged.connect(self._show)
        split.addWidget(self.list)

        right = QWidget()
        v = QVBoxLayout(right)
        v.setContentsMargins(10, 0, 0, 0)
        self.details = _hint_label("")
        v.addWidget(self.details)
        v.addWidget(QLabel("Typed text"))
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        v.addWidget(self.text, 3)
        self.raw_label = QLabel("As recognised, before AI processing")
        v.addWidget(self.raw_label)
        self.raw = QPlainTextEdit()
        self.raw.setReadOnly(True)
        v.addWidget(self.raw, 2)
        split.addWidget(right)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        root.addWidget(split, 1)

        buttons = QHBoxLayout()
        self.count = _hint_label("")
        buttons.addWidget(self.count, 1)
        self.copy_btn = QPushButton("Copy text")
        self.copy_btn.clicked.connect(lambda _=False: self._copy(self.text))
        self.copy_raw_btn = QPushButton("Copy recognised")
        self.copy_raw_btn.clicked.connect(lambda _=False: self._copy(self.raw))
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.clicked.connect(lambda _=False: self.delete_current())
        self.clear_btn = QPushButton("Clear all…")
        self.clear_btn.clicked.connect(lambda _=False: self.clear_all())
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        for b in (self.copy_btn, self.copy_raw_btn, self.delete_btn, self.clear_btn, close):
            buttons.addWidget(b)
        root.addLayout(buttons)

        self.refresh()

    # ── data ────────────────────────────────────────────────────────────
    def refresh(self):
        self._entries = history.load()
        self._filter()

    def _filter(self):
        current = self.current_entry()
        self._shown = history.search(self._entries, self.search.text())
        self.list.blockSignals(True)
        self.list.clear()
        for e in self._shown:
            self.list.addItem(QListWidgetItem(entry_title(e)))
        self.list.blockSignals(False)
        row = self._shown.index(current) if current in self._shown else (0 if self._shown else -1)
        self.list.setCurrentRow(row)
        self._show(row)

        total = len(self._entries)
        if not total:
            note = ("History is off (Settings → Application)."
                    if not self.cfg.data.get("history_enabled", True) else "No dictations yet.")
        elif len(self._shown) != total:
            note = f"{len(self._shown)} of {total}"
        else:
            days = int(self.cfg.data.get("history_days", 30) or 0)
            note = f"{total} dictation{'s' if total != 1 else ''}" + (
                f", kept for {days} days" if days > 0 else ", kept until cleared")
        self.count.setText(note)
        self.clear_btn.setEnabled(bool(total))

    def current_entry(self) -> dict | None:
        row = self.list.currentRow()
        return self._shown[row] if 0 <= row < len(self._shown) else None

    def _show(self, row: int):
        entry = self._shown[row] if 0 <= row < len(self._shown) else None
        self.details.setText(entry_details(entry) if entry else "")
        self.text.setPlainText(entry.get("text", "") if entry else "")
        raw = entry.get("raw", "") if entry else ""
        self.raw.setPlainText(raw)
        for w in (self.raw_label, self.raw, self.copy_raw_btn):
            w.setVisible(bool(raw))
        for b in (self.copy_btn, self.delete_btn):
            b.setEnabled(entry is not None)

    # ── actions ─────────────────────────────────────────────────────────
    def _copy(self, edit: QPlainTextEdit):
        text = edit.toPlainText()
        if not text:
            return
        try:
            from phonotype.core.clipboard import ClipboardManager
            ClipboardManager().copy(text)       # wl-copy: survives on Wayland
        except Exception:
            QApplication.clipboard().setText(text)
        self.count.setText("Copied.")
        QTimer.singleShot(1500, self._filter)

    def delete_current(self):
        entry = self.current_entry()
        if entry:
            history.delete(entry["ts"])
            self.refresh()

    def clear_all(self):
        answer = QMessageBox.question(
            self, "Clear history",
            f"Delete all {len(self._entries)} stored dictations? This cannot be undone.")
        if answer == QMessageBox.StandardButton.Yes:
            history.clear()
            self.refresh()


_window: HistoryWindow | None = None


def show_history_window(cfg, parent: QWidget | None = None) -> HistoryWindow:
    """Open the (single) history window, or bring it forward and refresh it."""
    global _window
    if _window is None or not _window.isVisible():
        _window = HistoryWindow(cfg, parent)
    else:
        _window.refresh()
    _window.show()
    _window.raise_()
    _window.activateWindow()
    return _window
