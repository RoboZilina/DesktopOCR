# Stage 1 — Source Window Selector (HWND Picker Dialog)

## Objective

Build a PyQt6 dialog that lists all visible top-level Windows windows (HWND + title), lets the user search/filter and select one, and returns the chosen HWND to the application runtime. This replaces the current terminal `input("Enter HWND...")` flow.

---

## Architecture

```
user clicks "Select Window" button
        │
        ▼
WindowPickerDialog (PyQt6 QDialog)
  ├── Enumerates windows via ctypes EnumWindows
  ├── Displays: [HWND (hex)] [Window Title]
  ├── Search/filter text field
  ├── Refresh button
  └── OK / Cancel buttons
        │
        ▼ (selected HWND)
ScreenCapture(hwnd) initialized
        │
        ▼
OCR pipeline runs as before
```

---

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `ui/window_picker.py` | **Create** | PyQt6 `WindowPickerDialog` class |
| `ui/__init__.py` | Modify | Export `WindowPickerDialog` |
| `ui/overlay.py` | Modify | Add `select_window()` helper method |
| `main.py` | Modify | Wire `--hwnd` CLI flag and/or launch picker on startup |

---

## Detailed Implementation

### 1. [`ui/window_picker.py`](ui/window_picker.py) — New file

```python
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
from PyQt6.QtCore import Qt, QTimer


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
```

### 2. [`ui/__init__.py`](ui/__init__.py) — Modify

**Append** to existing content (do not replace the file wholesale):

```python
from ui.window_picker import WindowPickerDialog
```

### 3. [`main.py`](main.py) — Wiring changes

**Keep** `--hwnd` CLI argument for debugging/backwards compatibility.
**Add** new entry modes:

```python
# If --hwnd is NOT provided, launch WindowPickerDialog
# If --hwnd is provided, use it directly (existing behavior)
```

The flow:

```
main()
  ├── parse_args()
  ├── if args.hwnd:
  │     hwnd = args.hwnd
  ├── else:
  │     app = QApplication.instance() or QApplication(sys.argv)
  │     dialog = WindowPickerDialog()
  │     if dialog.exec() == QDialog.DialogCode.Accepted:
  │         hwnd = dialog.selected_hwnd
  │     else:
  │         sys.exit("No window selected")
  │
  ├── ScreenCapture(hwnd)
  └── ... rest of main loop ...
```

**Important:** PyQt6 requires a `QApplication` instance before creating any widgets. Using `QApplication.instance() or QApplication(sys.argv)` ensures safe, idempotent initialization — it returns the existing instance if one already exists, avoiding crashes when `select_window()` is called from non-entry-point contexts. The existing `main.py` doesn't create one, so GUI mode must initialize it early.

Steps for the `main.py` wiring:

1. Create `QApplication` early if GUI mode is needed (safe idempotent pattern above)
2. Use `qasync` to integrate PyQt6 event loop with asyncio
3. Keep the terminal/CLI path for `--hwnd` mode without PyQt dependency

### 4. [`ui/overlay.py`](ui/overlay.py) — Modify

Add a `select_window()` static/class method that:
1. Creates `WindowPickerDialog`
2. Shows it modally
3. Returns selected HWND

---

## Dependencies

All already installed in `.venv`:
- `PyQt6==6.11.0`
- `qasync==0.28.0`

---

## Integration with Existing Code

### Web app → DesktopOCR mapping

| Web app (personalOCR-Cloudflare) | DesktopOCR (Python) |
|----------------------------------|---------------------|
| `navigator.mediaDevices.getDisplayMedia()` | `WindowPickerDialog` using `EnumWindows` |
| `videoStream = result` | `ScreenCapture(hwnd)` |
| `vnVideo.srcObject = videoStream` | Preview widget (Stage 2) |
| `selectWindowBtn.onclick` | `QPushButton.clicked.connect` |

### Edge cases handled

1. **No visible windows** → Show empty list + "No windows found" status
2. **User cancels** → Return `None`, app exits gracefully with message
3. **Window closed between listing and selection** → `ScreenCapture` will handle gracefully (returns None frames)
4. **DPI scaling** → PyQt6 handles High DPI automatically via `QtHighDpiScaleFactorRoundingPolicy`
5. **Search/filter** → Case-insensitive match on title and hex HWND
6. **Keyboard navigation** → Table supports arrow keys + Enter to accept

---

## Files to Modify Summary

| File | Change |
|------|--------|
| `ui/window_picker.py` | **New** — WindowPickerDialog class |
| `ui/__init__.py` | Add `from ui.window_picker import WindowPickerDialog` |
| `main.py` | Wire --hwnd or picker dialog entry path |
| `ui/overlay.py` | Add `select_window()` helper |

---

## Acceptance Criteria

1. [ ] Running `python main.py` (without `--hwnd`) opens the window picker dialog
2. [ ] Dialog lists all visible windows with HWND and title
3. [ ] Search/filter works in real-time as user types
4. [ ] Refresh button re-enumerates windows
5. [ ] Double-click or OK confirms selection, returns HWND
6. [ ] Cancel exits gracefully
7. [ ] `python main.py --hwnd 0x1234` bypasses the dialog and uses the CLI value
8. [ ] Window titles update correctly (no stale cache)
9. [ ] The existing OCR pipeline works identically after HWND selection

---

## Testing Notes

```bash
# GUI mode (opens picker)
python main.py

# CLI mode (direct HWND)
python main.py --hwnd 0x1A2B3C4

# List windows without launching (debug)
python -c "from ui.window_picker import WindowPickerDialog; ..."
```
