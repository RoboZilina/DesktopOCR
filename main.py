import argparse
import asyncio
import ctypes
import ctypes.wintypes
import logging
import time
from datetime import datetime

from core.engine_manager import EngineManager
from core.capture import ScreenCapture
from core.capture_pipeline import CapturePipeline
from logic.validator import is_valid_japanese, clean_ocr_output


def parse_args():
    parser = argparse.ArgumentParser(description="DesktopOCR console runner")
    parser.add_argument("--hwnd", type=str, help="Window handle (hex like 0x1A2B or decimal)")
    parser.add_argument("--debug-once", action="store_true", help="Run one raw OCR diagnostic pass before loop")
    parser.add_argument("--models-dir", type=str, default="models/paddle", help="Directory containing OCR model files")
    parser.add_argument("--det-model", type=str, default="PP-OCRv5_server_det_infer.onnx", help="Detection ONNX filename")
    parser.add_argument("--rec-model", type=str, default="PP-OCRv5_server_rec_infer.onnx", help="Recognition ONNX filename")
    parser.add_argument("--dict-file", type=str, default="japan_dict.txt", help="Dictionary filename")
    return parser.parse_args()

def list_windows():
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
        print(f"HWND: {hwnd:<10} (0x{hwnd:08X}) | Title: {title}")
    print("-----------------------")

async def main():
    args = parse_args()

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    list_windows()

    if args.hwnd:
        user_input = args.hwnd.strip()
    else:
        print("\nRun tests/test_capture.py first to find your game HWND if unsure.")
        user_input = input("Enter HWND (hex like 0x1A2B or decimal): ").strip()
    
    if not user_input:
        print("No HWND provided. Exiting.")
        return

    try:
        if user_input.lower().startswith("0x"):
            hwnd = int(user_input, 16)
        else:
            hwnd = int(user_input)
    except ValueError:
        logger.error("Invalid HWND value '%s'. Use decimal or hex like 0x1A2B.", user_input)
        return

    MODEL_CONFIG = {
        "det": args.det_model,
        "rec": args.rec_model,
        "dict": args.dict_file,
    }
    MODELS_DIR = args.models_dir

    logger.info(
        "Model config | dir=%s | det=%s | rec=%s | dict=%s",
        MODELS_DIR,
        MODEL_CONFIG["det"],
        MODEL_CONFIG["rec"],
        MODEL_CONFIG["dict"],
    )

    engine_manager = EngineManager(MODELS_DIR, MODEL_CONFIG)
    capture = ScreenCapture(hwnd)
    
    # default VN text box region config based on requirements
    capture.set_region(0, 540, 1280, 180)
  
    
    pipeline = CapturePipeline(engine_manager, capture)

    try:
        logger.info("Loading server engine...")
        success = await engine_manager.switch_engine("server")
        if not success:
            logger.error("Failed to load server engine.")
            return

        if args.debug_once:
            logger.info("Running one-shot OCR debug pass...")
            frame = await capture.get_frame()
            if frame is None:
                logger.warning("Debug pass: no frame returned (identical frame or capture failed).")
            else:
                logger.info(
                    "Debug frame | region=%s | shape=%s | bitblt_fallback=%s",
                    getattr(capture, "_region", None),
                    getattr(frame, "shape", None),
                    getattr(capture, "_use_bitblt", False),
                )

                ocr_impl = getattr(engine_manager, "_current_instance", None)
                if ocr_impl is not None and hasattr(ocr_impl, "detect"):
                    det_t0 = time.perf_counter()
                    boxes = await ocr_impl.detect(frame)
                    det_ms = (time.perf_counter() - det_t0) * 1000.0
                    logger.info("Debug detect | boxes=%d | time_ms=%.1f", len(boxes), det_ms)

                ocr_t0 = time.perf_counter()
                raw = await engine_manager.run_ocr(frame)
                ocr_ms = (time.perf_counter() - ocr_t0) * 1000.0
                raw_text = raw.get("text", "")
                raw_conf = raw.get("confidence", 0.0)
                valid = is_valid_japanese(raw_text, raw_conf)
                cleaned = clean_ocr_output(raw_text)
                logger.info(
                    "Debug raw OCR | conf=%.3f | time_ms=%.1f | text=%r",
                    raw_conf,
                    ocr_ms,
                    raw_text,
                )
                logger.info(
                    "Debug validator | valid=%s | cleaned=%r",
                    valid,
                    cleaned,
                )

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
