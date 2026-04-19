import asyncio
import ctypes
import logging
from datetime import datetime

from core.engine_manager import EngineManager
from core.capture import ScreenCapture
from core.capture_pipeline import CapturePipeline

def list_windows():
    EnumWindows = ctypes.windll.user32.EnumWindows
    import ctypes.wintypes
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
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
                windows.append((hwnd, buff.value))
        return True

    EnumWindows(EnumWindowsProc(foreach_window), 0)
    
    print("--- Visible Windows ---")
    for hwnd, title in windows:
        print(f"HWND: {hwnd:<10} (0x{hwnd:08X}) | Title: {title}")
    print("-----------------------")

async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    list_windows()

    print("\nRun tests/test_capture.py first to find your game HWND if unsure.")
    user_input = input("Enter HWND (hex like 0x1A2B or decimal): ").strip()
    
    if not user_input:
        print("No HWND provided. Exiting.")
        return

    if user_input.lower().startswith("0x"):
        hwnd = int(user_input, 16)
    else:
        hwnd = int(user_input)

    MODEL_CONFIG = {
        "det": "PP-OCRv5_server_det_infer.onnx",
        "rec": "PP-OCRv5_server_rec_infer.onnx",
        "dict": "japan_dict.txt",
    }
    MODELS_DIR = "models/paddle"

    engine_manager = EngineManager(MODELS_DIR, MODEL_CONFIG)
    capture = ScreenCapture(hwnd)
    
    # default VN text box region config based on requirements
    capture.set_region(0, 0, 800, 200)  
    
    pipeline = CapturePipeline(engine_manager, capture)

    try:
        logger.info("Loading server engine...")
        success = await engine_manager.switch_engine("server")
        if not success:
            logger.error("Failed to load server engine.")
            return

        logger.info("Engine ready. Starting capture loop (Ctrl+C to stop)...")
        while True:
            res = await pipeline.capture_once()
            
            if res is not None:
                text = res.get("text", "")
                conf = res.get("confidence", 0.0)
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"\n[{timestamp}] [Conf: {conf:.2f}] {text}")
            else:
                # Silently log invalid strings inline mapped natively via terminal dot increments
                print(".", end="", flush=True)

            await asyncio.sleep(1.5)

    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        print("\nCleaning up resources...")
        capture.stop()
        await engine_manager.dispose_all()
        print("Stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
