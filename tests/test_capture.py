import asyncio
import ctypes
import sys
import os

# Ensure the root directory is on the path so we can import core module successfully
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import cv2
from core.capture import ScreenCapture

def list_windows():
    EnumWindows = ctypes.windll.user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
    GetWindowText = ctypes.windll.user32.GetWindowTextW
    GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
    IsWindowVisible = ctypes.windll.user32.IsWindowVisible

    windows = []
    def foreach_window(hwnd, lParam):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLength(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                GetWindowText(hwnd, buff, length + 1)
                windows.append((int(hwnd), buff.value))
        return True

    EnumWindows(EnumWindowsProc(foreach_window), 0)
    
    print("--- Visible Windows ---")
    for hwnd, title in windows:
        print(f"HWND: {hwnd:<10} (0x{hwnd:08X}) | Title: {title}")
    print("-----------------------")

async def main():
    list_windows()
    
    user_input = input("\nEnter HWND (hex like 0x1A2B or decimal): ").strip()
    if not user_input:
        print("No HWND provided. Exiting.")
        return

    if user_input.lower().startswith("0x"):
        hwnd = int(user_input, 16)
    else:
        hwnd = int(user_input)
        
    print(f"Initializing ScreenCapture for HWND {hwnd} (0x{hwnd:08X})")
    capture = ScreenCapture(hwnd)
    capture.set_region(0, 0, 800, 200)
    
    try:
        print("Attempting to capture frame...")
        frame = await capture.get_frame()
        
        if frame is None:
            print("Frame was None - identical frame or capture failed")
        else:
            print(f"Frame successfully returned! Shape: {frame.shape}, Dtype: {frame.dtype}")
            print("Press any key in the cv2 window to exit")
            
            cv2.imshow("Capture Test", frame)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
            
    except Exception as e:
        print(f"WinRT Native Capture Failure: {e}")
        import traceback
        traceback.print_exc()
    finally:
        capture.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
