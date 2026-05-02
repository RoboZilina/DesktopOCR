import asyncio
import os
import sys

# Ensure the root directory is on the path so we can import core module successfully
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import cv2
from core.capture import ScreenCapture
from core.win_utils import list_windows

async def main():
    list_windows()

    try:
        user_input = input("\nEnter HWND (hex like 0x1A2B or decimal): ").strip()
    except EOFError:
        print("No interactive input detected (EOF). Run this manually in a terminal and enter a HWND.")
        return

    if not user_input:
        print("No HWND provided. Exiting.")
        return

    try:
        if user_input.lower().startswith("0x"):
            hwnd = int(user_input, 16)
        else:
            hwnd = int(user_input)
    except ValueError:
        print(f"Invalid HWND value: '{user_input}'. Use decimal or hex like 0x1A2B.")
        return
        
    print(f"Initializing ScreenCapture for HWND {hwnd} (0x{hwnd:08X})")
    capture = ScreenCapture(hwnd)
    capture.set_region(0, 540, 1280, 180)

    
    try:
        print("Attempting to capture frame...")
        frame = await capture.get_frame()
        if getattr(capture, "_use_bitblt", False):
            print("WinRT failed during init. Capture is running on BitBlt fallback.")
        
        if frame is None:
            print("Frame was None - identical frame or capture failed")
        else:
            print(f"Frame successfully returned! Shape: {frame.shape}, Dtype: {frame.dtype}")
            print("Press any key in the cv2 window to exit")
            
            cv2.imshow("Capture Test", frame)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
            
    except Exception as e:
        print(f"Capture test failed: {e}")
        print("If this is WinRT-related, debug winsdk/GraphicsCapture first, then verify BitBlt fallback.")
        import traceback
        traceback.print_exc()
    finally:
        capture.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass