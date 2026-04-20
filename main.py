import argparse
import asyncio
import ctypes
import ctypes.wintypes
import logging
import math
import os
import pathlib
import time
from datetime import datetime
import cv2

from core.engine_manager import EngineManager
from core.capture import ScreenCapture
from core.capture_pipeline import CapturePipeline
from core.tensor_utils import preprocess_paddle_slice


def parse_args():
    parser = argparse.ArgumentParser(description="DesktopOCR console runner")
    parser.add_argument("--hwnd", type=str, help="Window handle (hex like 0x1A2B or decimal)")
    parser.add_argument("--debug-once", action="store_true", help="Run one raw OCR diagnostic pass before loop")
    parser.add_argument("--show-canvas", action="store_true", help="Show live OCR canvas with detection boxes")
    parser.add_argument("--raw-ocr", action="store_true", help="Disable validator/fallback/scoring and use raw detect+recognize")
    parser.add_argument("--light-preprocess", action="store_true", help="Apply light contrast bump + border pad before OCR tensors")
    parser.add_argument("--det-no-pad", action="store_true", help="Disable detector box padding for geometry debugging")
    parser.add_argument("--region", type=str, help="Capture region as x,y,w,h")
    parser.add_argument("--select-region", action="store_true", help="Interactively select capture region on first frame")
    parser.add_argument("--models-dir", type=str, default="models/paddle", help="Directory containing OCR model files")
    parser.add_argument("--det-model", type=str, default="PP-OCRv5_server_det_infer.onnx", help="Detection ONNX filename")
    parser.add_argument("--rec-model", type=str, default="PP-OCRv5_server_rec_infer.onnx", help="Recognition ONNX filename")
    parser.add_argument("--dict-file", type=str, default="japan_dict.txt", help="Dictionary filename")
    return parser.parse_args()


def _parse_region_arg(region_arg: str) -> tuple[int, int, int, int]:
    parts = [p.strip() for p in region_arg.split(",")]
    if len(parts) != 4:
        raise ValueError("Region must have exactly 4 comma-separated integers: x,y,w,h")
    x, y, w, h = [int(v) for v in parts]
    if w <= 0 or h <= 0:
        raise ValueError("Region width and height must be > 0")
    return x, y, w, h

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

    if args.raw_ocr:
        os.environ["DESKTOCR_RAW_OCR_MODE"] = "1"
        os.environ["DESKTOCR_DISABLE_VALIDATOR"] = "1"
    if args.light_preprocess:
        os.environ["DESKTOCR_LIGHT_PREPROCESS"] = "1"
    if args.det_no_pad:
        os.environ["DESKTOCR_DET_NO_PAD"] = "1"

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
    logger.info(
        "Runtime flags | raw_ocr=%s | light_preprocess=%s | det_no_pad=%s | web_parity=%s",
        os.getenv("DESKTOCR_RAW_OCR_MODE", "0"),
        os.getenv("DESKTOCR_LIGHT_PREPROCESS", "0"),
        os.getenv("DESKTOCR_DET_NO_PAD", "0"),
        os.getenv("DESKTOCR_WEB_PARITY_MODE", "0"),
    )
    logger.info("Active mode | baseline-reset")

    engine_manager = EngineManager(MODELS_DIR, MODEL_CONFIG)
    capture = ScreenCapture(hwnd)

    # Region selection priority:
    # 1) Explicit --region x,y,w,h
    # 2) Interactive --select-region
    # 3) Backward-compatible default
    selected_region = None
    if args.region:
        try:
            selected_region = _parse_region_arg(args.region)
            logger.info("Using CLI region: %s", selected_region)
        except ValueError as exc:
            logger.error("Invalid --region value '%s': %s", args.region, exc)
            return
    elif args.select_region:
        logger.info("Interactive region selection enabled. Capturing preview frame...")
        preview = await capture.get_frame()
        if preview is None:
            logger.error("Failed to capture preview frame for region selection.")
            return

        x, y, w, h = cv2.selectROI("Select OCR Region", preview, showCrosshair=True, fromCenter=False)
        cv2.destroyWindow("Select OCR Region")
        if w <= 0 or h <= 0:
            logger.error("Region selection canceled or invalid (w/h <= 0).")
            return
        selected_region = (int(x), int(y), int(w), int(h))
        logger.info("Selected region: %s", selected_region)

    if selected_region is None:
        selected_region = (0, 540, 1280, 180)
        logger.info("Using default region: %s", selected_region)

    capture.set_region(*selected_region)
  
    
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
                    debug_frame = preprocess_paddle_slice(frame)
                    boxes = await ocr_impl.detect(debug_frame)
                    det_ms = (time.perf_counter() - det_t0) * 1000.0
                    logger.info("Debug detect | boxes=%d | time_ms=%.1f", len(boxes), det_ms)

                    dbg_dir = pathlib.Path("debug_ocr")
                    dbg_dir.mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(dbg_dir / "debug_once_preprocessed.png"), debug_frame)

                    full_rec = await ocr_impl.recognize(debug_frame)
                    logger.info(
                        "Debug full-slice rec | conf=%.3f | text=%r",
                        float(full_rec.get("confidence", 0.0) or 0.0),
                        (full_rec.get("text", "") or ""),
                    )

                    h_dbg, w_dbg = debug_frame.shape[:2]
                    for i, b in enumerate(boxes):
                        x1 = max(0, int(math.floor(float(b[0]))))
                        y1 = max(0, int(math.floor(float(b[1]))))
                        x2 = min(w_dbg, int(math.ceil(float(b[2]))))
                        y2 = min(h_dbg, int(math.ceil(float(b[3]))))
                        if x2 - x1 < 4 or y2 - y1 < 4:
                            continue
                        crop = debug_frame[y1:y2, x1:x2].copy()
                        cv2.imwrite(str(dbg_dir / f"debug_once_box_{i:02d}.png"), crop)

                    overlay = debug_frame.copy()
                    for b in boxes:
                        x1 = int(math.floor(float(b[0])))
                        y1 = int(math.floor(float(b[1])))
                        x2 = int(math.ceil(float(b[2])))
                        y2 = int(math.ceil(float(b[3])))
                        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.imwrite(str(dbg_dir / "debug_once_overlay.png"), overlay)
                    logger.info("Debug artifacts written to: %s", dbg_dir.resolve())

                ocr_t0 = time.perf_counter()
                raw = await engine_manager.run_ocr(frame)
                ocr_ms = (time.perf_counter() - ocr_t0) * 1000.0
                raw_text = raw.get("text", "")
                raw_conf = raw.get("confidence", 0.0)
                logger.info(
                    "Debug raw OCR | conf=%.3f | time_ms=%.1f | text=%r",
                    raw_conf,
                    ocr_ms,
                    raw_text,
                )

        logger.info("Engine ready. Starting capture loop (Ctrl+C to stop)...")
        last_shown_text = ""
        while True:
            if args.show_canvas:
                frame = await capture.get_frame()
                if frame is None:
                    print(".", end="", flush=True)
                    await asyncio.sleep(1.5)
                    continue

                ocr_impl = getattr(engine_manager, "_current_instance", None)
                canvas_frame = preprocess_paddle_slice(frame)
                raw_boxes = []
                if ocr_impl is not None and hasattr(ocr_impl, "detect"):
                    raw_boxes = await ocr_impl.detect(canvas_frame)

                vis = canvas_frame.copy()
                for b in raw_boxes:
                    x1 = int(math.floor(float(b[0])))
                    y1 = int(math.floor(float(b[1])))
                    x2 = int(math.ceil(float(b[2])))
                    y2 = int(math.ceil(float(b[3])))
                    cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)

                cv2.putText(
                    vis,
                    f"detected={len(raw_boxes)} recognized={len(raw_boxes)}",
                    (8, 22),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )
                cv2.imshow("OCR Canvas", vis)
                cv2.waitKey(1)

                res = await engine_manager.run_ocr(frame)
                text = (res.get("text", "") or "").strip()
                conf = float(res.get("confidence", 0.0) or 0.0)
                if text and text != last_shown_text:
                    last_shown_text = text
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"\n[{timestamp}] [Conf: {conf:.2f}] {text}")
                else:
                    print(".", end="", flush=True)

                await asyncio.sleep(1.5)
                continue

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
        cv2.destroyAllWindows()
        capture.stop()
        await engine_manager.dispose_all()
        print("Stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
