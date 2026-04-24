import argparse
import asyncio
import ctypes
import ctypes.wintypes
import logging
import math
import os
import pathlib
import sys
import time
from collections import deque
from datetime import datetime
import cv2

from core.engine_manager import EngineManager
from core.capture import ScreenCapture
from core.capture_pipeline import CapturePipeline
from core.tensor_utils import preprocess_paddle_slice


def parse_args():
    parser = argparse.ArgumentParser(description="DesktopOCR console runner")
    parser.add_argument("--engine", type=str, default="paddle", choices=["paddle", "windows_ocr", "easyocr"], help="OCR engine to use")
    parser.add_argument("--list-engines", action="store_true", help="List available engine IDs and exit")
    parser.add_argument("--list-engine-status", action="store_true", help="List engine IDs with readiness/dependency status and exit")
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
        safe_title = title.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding)
        print(f"HWND: {hwnd:<10} (0x{hwnd:08X}) | Title: {safe_title}")
    print("-----------------------")

async def main(
    hwnd: int,
    gui_mode: bool = False,
    frame_queue=None,
    status_bar=None,
    preview=None,
    window=None,
):
    args = parse_args()

    engine_manager = EngineManager("models/paddle", {"det": "", "rec": "", "dict": ""})

    if args.list_engines:
        print("Available engines:")
        for engine_id in engine_manager.get_supported_engines():
            print(f"- {engine_id}")
        return

    if args.list_engine_status:
        print("Engine status:")
        statuses = engine_manager.get_engine_status()
        for engine_id in engine_manager.get_supported_engines():
            info = statuses.get(engine_id, {})
            state = info.get("state", "unknown")
            dependency = info.get("dependency")
            note = info.get("note")
            suffix_parts = []
            if dependency:
                suffix_parts.append(f"dependency={dependency}")
            if note:
                suffix_parts.append(f"note={note}")
            suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
            print(f"- {engine_id}: state={state}{suffix}")
        return

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
        "Runtime flags | engine=%s | raw_ocr=%s | light_preprocess=%s | det_no_pad=%s | web_parity=%s",
        args.engine,
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
        preview_frame = await capture.get_frame()
        if preview_frame is None:
            logger.error("Failed to capture preview frame for region selection.")
            return

        x, y, w, h = cv2.selectROI("Select OCR Region", preview_frame, showCrosshair=True, fromCenter=False)
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
        logger.info("Loading engine: %s ...", args.engine)
        success = await engine_manager.switch_engine(args.engine)
        if not success:
            logger.error("Failed to load engine: %s", args.engine)
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
                if engine_manager.current_id == "paddle" and ocr_impl is not None and hasattr(ocr_impl, "detect"):
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
                else:
                    logger.info("Debug detect overlay skipped (selected engine does not expose Paddle detect boxes).")

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

        # ---- GUI mode capture loop --------------------------------
        if gui_mode:
            from PyQt6.QtWidgets import QApplication

            logger.info("Starting GUI capture loop...")

            # CloseEvent handler: flag the loop to stop when window is closed
            # TODO(Stage 4): replace with qasync shutdown
            _gui_running = True
            def _on_close():
                nonlocal _gui_running
                _gui_running = False
            window.closeEvent = lambda e: (_on_close(), e.accept())

            # Connect overlay selection to capture region updates
            def _on_region_changed(nx, ny, nw, nh):
                imgW, imgH = preview.frame_size
                if imgW == 0 or imgH == 0:
                    return
                x = int(nx * imgW)
                y = int(ny * imgH)
                w = int(nw * imgW)
                h = int(nh * imgH)
                capture.set_region(x, y, w, h)
                logger.info("Region selected: x=%d y=%d w=%d h=%d", x, y, w, h)

            preview.selection_overlay.region_changed.connect(_on_region_changed)

            while _gui_running:
                frame = await capture.get_frame(full=True)
                if frame is not None:
                    # Push full window frame into deque for preview widget
                    frame_queue.append(frame.copy())

                    # Run OCR
                    res = await pipeline.capture_once()
                    if res is not None:
                        text = res.get("text", "")
                        conf = res.get("confidence", 0.0)
                        meta = res.get("meta", {}) if isinstance(res, dict) else {}
                        engine_id = meta.get("engine", engine_manager.current_id)
                        status_bar.set_engine(engine_id)
                        status_bar.set_confidence(float(conf))
                        if text:
                            status_bar.set_window_title(text[:60])
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        print(f"\n[{timestamp}] [{engine_id}] [Conf: {conf:.2f}] {text}")

                # Pump Qt events -- critical for preview responsiveness
                # Placed BEFORE sleep to prevent 1.5s UI freeze
                QApplication.processEvents()

                await asyncio.sleep(1.5)

            # Cleanup on window close
            preview.stop()
            window.close()
            logger.info("GUI window closed. Stopping capture.")
            return

        while True:
            if args.show_canvas:
                frame = await capture.get_frame()
                if frame is None:
                    print(".", end="", flush=True)
                    await asyncio.sleep(1.5)
                    continue

                ocr_impl = getattr(engine_manager, "_current_instance", None)
                is_paddle = engine_manager.current_id == "paddle"
                canvas_frame = preprocess_paddle_slice(frame) if is_paddle else frame
                raw_boxes = []
                if is_paddle and ocr_impl is not None and hasattr(ocr_impl, "detect"):
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
                    f"engine={engine_manager.current_id} detected={len(raw_boxes)}",
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
                meta = res.get("meta", {}) if isinstance(res, dict) else {}
                validator = meta.get("validator", {}) if isinstance(meta, dict) else {}
                v_enabled = bool(validator.get("enabled", False))
                v_changed = bool(validator.get("changed", False))
                v_valid = bool(validator.get("valid_hint", False))
                engine_id = meta.get("engine", engine_manager.current_id)
                if text and text != last_shown_text:
                    last_shown_text = text
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(
                        f"\n[{timestamp}] [Engine: {engine_id}] [Conf: {conf:.2f}] "
                        f"[Val: {'on' if v_enabled else 'off'}, changed={v_changed}, ok={v_valid}] {text}"
                    )
                else:
                    print(".", end="", flush=True)

                await asyncio.sleep(1.5)
                continue

            res = await pipeline.capture_once()
            
            if res is not None:
                text = res.get("text", "")
                conf = res.get("confidence", 0.0)
                meta = res.get("meta", {}) if isinstance(res, dict) else {}
                validator = meta.get("validator", {}) if isinstance(meta, dict) else {}
                v_enabled = bool(validator.get("enabled", False))
                v_changed = bool(validator.get("changed", False))
                v_valid = bool(validator.get("valid_hint", False))
                engine_id = meta.get("engine", engine_manager.current_id)
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(
                    f"\n[{timestamp}] [Engine: {engine_id}] [Conf: {conf:.2f}] "
                    f"[Val: {'on' if v_enabled else 'off'}, changed={v_changed}, ok={v_valid}] {text}"
                )
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

def _resolve_hwnd_from_arg(value: str, logger: logging.Logger) -> int | None:
    """Parse hex (0x...) or decimal HWND string. Returns None on failure."""
    user_input = value.strip()
    if not user_input:
        logger.error("Empty HWND value.")
        return None
    try:
        # int(val, 0) auto-detects base: 0x prefix → hex, otherwise decimal
        return int(user_input, 0)
    except ValueError:
        logger.error("Invalid HWND value '%s'. Use decimal or hex like 0x1A2B.", user_input)
        return None


if __name__ == "__main__":
    args = parse_args()

    # Early-exit flags that don't need a HWND
    if args.list_engines or args.list_engine_status:
        asyncio.run(main(0))  # hwnd unused for listing
        sys.exit(0)

    # Determine mode: GUI mode when --hwnd is NOT provided
    gui_mode = args.hwnd is None

    # QApplication is always needed for the picker dialog (and preview in GUI mode)
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    # Resolve HWND: --hwnd flag or GUI picker dialog
    hwnd: int | None = None
    if args.hwnd:
        hwnd = _resolve_hwnd_from_arg(args.hwnd, logging.getLogger(__name__))
    else:
        from PyQt6.QtWidgets import QDialog
        from ui.window_picker import WindowPickerDialog
        dialog = WindowPickerDialog()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            hwnd = dialog.selected_hwnd

    if hwnd is None:
        sys.exit("No window selected. Use --hwnd or run without it to open the picker.")

    # GUI mode: create preview window before starting capture
    if gui_mode:
        from PyQt6.QtWidgets import QMainWindow, QVBoxLayout, QWidget as QCentralWidget
        from ui.preview_widget import PreviewWidget
        from ui.components import StatusBar

        window = QMainWindow()
        window.setWindowTitle(f"DesktopOCR \u2014 {hex(hwnd)}")
        window.setMinimumSize(640, 480)

        central = QCentralWidget()
        window.setCentralWidget(central)
        layout = QVBoxLayout(central)

        frame_queue: deque = deque(maxlen=1)
        preview = PreviewWidget(frame_queue)
        layout.addWidget(preview, stretch=1)

        status_bar = StatusBar()
        layout.addWidget(status_bar)

        window.show()
    else:
        frame_queue = None
        preview = None
        status_bar = None
        window = None

    try:
        asyncio.run(
            main(
                hwnd,
                gui_mode=gui_mode,
                frame_queue=frame_queue,
                status_bar=status_bar,
                preview=preview,
                window=window,
            )
        )
    except KeyboardInterrupt:
        pass
