"""Windows utility functions — window enumeration, etc."""

import ctypes
import ctypes.wintypes
import sys


def list_windows():
    """Enumerate all visible top-level windows and print them to stdout."""
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

    print("--- Visible Windows ---")
    for hwnd, title in windows:
        encoding = sys.stdout.encoding or "utf-8"
        safe_title = title.encode(encoding, errors="replace").decode(encoding)
        print(f"HWND: {hwnd:<10} (0x{hwnd:08X}) | Title: {safe_title}")
    print("-----------------------")
