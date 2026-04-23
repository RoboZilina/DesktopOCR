"""PyQt6 transparent, frameless, always-on-top overlay window for the VN capture region."""

from PyQt6.QtWidgets import QApplication, QDialog
import sys


def select_window() -> int | None:
    """
    Show the WindowPickerDialog modally and return the selected HWND.

    Creates QApplication if one doesn't exist yet (idempotent).
    Returns the selected HWND as int, or None if the dialog was canceled.
    """
    app = QApplication.instance() or QApplication(sys.argv)
    from ui.window_picker import WindowPickerDialog

    dialog = WindowPickerDialog()
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.selected_hwnd
    return None
