"""
PyQt6 modal dialog for selecting a visible window by HWND.

Mirrors the web app's "Select Window Source" button behavior.
On web: navigator.mediaDevices.getDisplayMedia() shows browser-native picker.
On desktop: we enumerate visible windows via EnumWindows and present them in a list.
"""

import ctypes
import ctypes.wintypes
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QMessageBox,
)
from PyQt6.QtCore import Qt


class WindowPickerDialog(QDialog):
    """
    Modal dialog listing visible top-level windows.

    Returns selected HWND as int via .selected_hwnd property,
    or None if dialog was canceled.
    """

    COL_HWND = 0
    COL_TITLE = 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Window Source")
        self.setMinimumSize(600, 400)
        self.setModal(True)

        self._selected_hwnd: int | None = None
        self._selected_title: str | None = None
        self._windows: list[tuple[int, str]] = []

        self._build_ui()
        self._refresh_windows()

    # ---- UI construction ----

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Search / filter
        search_layout = QHBoxLayout()
        self._search_field = QLineEdit()
        self._search_field.setPlaceholderText("Filter windows by title...")
        self._search_field.textChanged.connect(self._apply_filter)
        search_layout.addWidget(self._search_field)

        self._refresh_btn = QPushButton("🔄 Refresh")
        self._refresh_btn.clicked.connect(self._refresh_windows)
        search_layout.addWidget(self._refresh_btn)
        layout.addLayout(search_layout)

        # Window table
        self._table = QTableWidget()
        self._table.setColumnCount(2)
        self._table.setHorizontalHeaderLabels(["HWND", "Window Title"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self._table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._table.doubleClicked.connect(self._accept_selection)
        self._table.currentItemChanged.connect(
            lambda: self._ok_btn.setEnabled(self._table.currentRow() >= 0)
        )
        layout.addWidget(self._table)

        # Status label
        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        # OK / Cancel buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._ok_btn = QPushButton("OK")
        self._ok_btn.clicked.connect(self._accept_selection)
        self._ok_btn.setEnabled(False)
        btn_layout.addWidget(self._ok_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    # ---- Window enumeration ----

    def _refresh_windows(self):
        """Enumerate visible windows via EnumWindows."""
        user32 = ctypes.windll.user32
        EnumWindows = user32.EnumWindows
        GetWindowTextW = user32.GetWindowTextW
        GetWindowTextLengthW = user32.GetWindowTextLengthW
        IsWindowVisible = user32.IsWindowVisible

        WNDENUMPROC = ctypes.WINFUNCTYPE(
            ctypes.wintypes.BOOL,
            ctypes.wintypes.HWND,
            ctypes.wintypes.LPARAM,
        )

        windows: list[tuple[int, str]] = []

        def foreach_window(hwnd: int, _l_param) -> bool:
            if IsWindowVisible(hwnd):
                length = GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    GetWindowTextW(hwnd, buff, length + 1)
                    windows.append((int(hwnd), buff.value))
            return True

        EnumWindows(WNDENUMPROC(foreach_window), 0)

        self._windows = windows
        self._apply_filter()

    def _apply_filter(self):
        """Filter displayed rows by search text."""
        query = self._search_field.text().strip().lower()
        filtered = self._windows
        if query:
            filtered = [
                (hwnd, title)
                for hwnd, title in self._windows
                if query in title.lower()
                or query in hex(hwnd).lower()
            ]

        self._table.setRowCount(0)
        for hwnd, title in filtered:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, self.COL_HWND, QTableWidgetItem(f"0x{hwnd:08X}"))
            self._table.setItem(row, self.COL_TITLE, QTableWidgetItem(title))

        self._status_label.setText(
            f"Showing {len(filtered)} of {len(self._windows)} windows"
        )

    # ---- Selection handling ----

    def _accept_selection(self):
        row = self._table.currentRow()
        if row < 0:
            QMessageBox.information(self, "No Selection", "Please select a window first.")
            return
        hwnd_item = self._table.item(row, self.COL_HWND)
        title_item = self._table.item(row, self.COL_TITLE)
        if hwnd_item is None:
            return
        self._selected_hwnd = int(hwnd_item.text(), 16)
        self._selected_title = title_item.text() if title_item else None
        self.accept()

    @property
    def selected_hwnd(self) -> int | None:
        return self._selected_hwnd

    @property
    def selected_title(self) -> str | None:
        return self._selected_title
