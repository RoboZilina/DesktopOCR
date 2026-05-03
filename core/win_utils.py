"""Windows utility functions — window enumeration, etc."""

import ctypes
import ctypes.wintypes
import logging
import sys

logger = logging.getLogger(__name__)


def list_windows():
    """Enumerate all visible top-level windows and log them."""
    user32 = ctypes.windll.user32
    EnumWindows = user32.EnumWindows
    GetWindowText = user32.GetWindowTextW
    GetWindowTextLength = user32.GetWindowTextLengthW
    IsWindowVisible = user32.IsWindowVisible

    WNDENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.wintypes.BOOL,
        ctypes.wintypes.HWND,
        ctypes.wintypes.LPARAM,
    )

    windows = []
    def foreach_window(hwnd, l_param):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLength(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                GetWindowText(hwnd, buff, length + 1)
                windows.append((int(hwnd), buff.value))
        return True

    EnumWindows(WNDENUMPROC(foreach_window), 0)

    logger.info("--- Visible Windows ---")
    for hwnd, title in windows:
        logger.info("HWND: %-10d (0x%08X) | Title: %s", hwnd, hwnd, title)
    logger.info("-----------------------")
