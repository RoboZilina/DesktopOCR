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
import numpy as np

from tts.manager import TTSManager
from tts.openjtalk_backend import OpenJTalkBackend
from tts.voicevox_backend import VoiceVoxBackend

DIFF_THRESHOLD = 8.0
PREVIEW_INTERVAL = 0.25
STABILIZE_DELAY = 0.5

def _compute_diff(frame: np.ndarray, ref: np.ndarray | None) -> float:
    """Return mean absolute pixel difference between two BGR frames."""
    if ref is None or frame.shape != ref.shape:
        return 999.0
    gray1 = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
    return float(np.mean(np.abs(gray1.astype(np.int16) - gray2.astype(np.int16))))


def _manual_crop(frame: np.ndarray, region: tuple[int, int, int, int]) -> np.ndarray:
    """Crop frame to region (x, y, w, h).  Clamps to frame bounds."""
    x, y, w, h = region
    fh, fw = frame.shape[:2]
    x = max(0, x)
    y = max(0, y)
    w = max(1, min(w, fw - x))
    h = max(1, min(h, fh - y))
    return frame[y:y + h, x:x + w]

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

async def main(hwnd, gui_mode=True, window=None, window_title=""):
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

        # ---- GUI controls setup -----------------------------------
        if gui_mode:
            async def _on_engine_changed(engine_id: str):
                ok = await engine_manager.switch_engine(engine_id)
                if ok:
                    window.set_status(engine_id, 0.0, 0.0, window_title or hex(hwnd))

            window.engine_changed.connect(
                lambda eid: asyncio.ensure_future(_on_engine_changed(eid))
            )

            # Stub translate handler — print to terminal for now
            def _on_translate_requested(text: str):
                print(f"[Translate stub] {text}")

            window.translate_requested.connect(_on_translate_requested)

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
            logger.info("Starting GUI capture loop...")

            stop_event = asyncio.Event()
            def _on_close(e):
                stop_event.set()
                e.accept()
            window.closeEvent = _on_close

            # Connect overlay selection to capture region updates
            def _on_region_changed(nx, ny, nw, nh):
                imgW, imgH = window.preview_widget.frame_size
                if imgW == 0 or imgH == 0:
                    return
                x = int(nx * imgW)
                y = int(ny * imgH)
                w = int(nw * imgW)
                h = int(nh * imgH)
                capture.set_region(x, y, w, h)
                logger.info("Region selected: x=%d y=%d w=%d h=%d", x, y, w, h)

            window.preview_widget.selection_overlay.region_changed.connect(_on_region_changed)

            # Mutable settings container — accessible from lambda callbacks
            settings = {
                "auto_capture": True,
                "auto_copy": False,
                "vn_cleaner": True,
                "diff_threshold": DIFF_THRESHOLD,
            }

            # Wire side menu toggles
            window.side_menu.auto_capture_changed.connect(
                lambda v: settings.__setitem__("auto_capture", v)
            )
            window.side_menu.auto_copy_changed.connect(
                lambda v: settings.__setitem__("auto_copy", v)
            )
            window.side_menu.history_visible_changed.connect(window.history_sidebar.setVisible)
            window.side_menu.preview_visible_changed.connect(window.preview_widget.setVisible)
            window.side_menu.text_size_changed.connect(window.transcription_tray.set_text_size)
            window.side_menu.tray_height_changed.connect(window.transcription_tray.set_tray_height)
            window.side_menu.vn_cleaner_changed.connect(
                lambda v: (
                    settings.__setitem__("vn_cleaner", v),
                    os.environ.pop("DESKTOCR_DISABLE_VALIDATOR", None) if v else os.environ.__setitem__("DESKTOCR_DISABLE_VALIDATOR", "1"),
                )
            )
            window.side_menu.diff_threshold_changed.connect(
                lambda v: settings.__setitem__("diff_threshold", v)
            )
            window.side_menu.reset_requested.connect(
                lambda: [
                    settings.update({"auto_capture": True, "auto_copy": False, "vn_cleaner": True, "diff_threshold": 8.0}),
                    window.side_menu.auto_capture_changed.emit(True),
                    window.side_menu.auto_copy_changed.emit(False),
                    window.side_menu.vn_cleaner_changed.emit(True),
                    window.side_menu.diff_threshold_changed.emit(8.0),
                ]
            )

            # TTS manager (OpenJTalk active, VoiceVox fallback)
            tts = TTSManager([
                OpenJTalkBackend(),
                VoiceVoxBackend(),
            ])
            tts.set_backend("coeiroink")
            window.tts_requested.connect(tts.speak)

            # Populate voice selector from TTS backend
            voices = tts.list_voices()
            window.controls_bar.load_voices(voices)
            window.controls_bar.voice_changed.connect(lambda vid: tts.set_voice(vid))

            ocr_trigger = asyncio.Event()

            # Wire re-capture button in tray to force immediate OCR
            window.recapture_requested.connect(ocr_trigger.set)
            ref_frame: np.ndarray | None = None
            _capture_gen = 0  # incremented on each OCR trigger; stale results discarded

            async def _preview_task():
                nonlocal ref_frame
                _stabilize_task: asyncio.Task | None = None

                async def _trigger_after_stabilize():
                    await asyncio.sleep(STABILIZE_DELAY)
                    ocr_trigger.set()

                while not stop_event.is_set():
                    full_frame = await capture.get_frame(full=True)
                    if full_frame is not None:
                        window.set_preview_frame(full_frame)
                        if settings["auto_capture"]:
                            region = capture.region or (0, 0, full_frame.shape[1], full_frame.shape[0])
                            crop_frame = _manual_crop(full_frame, region)
                            diff = _compute_diff(crop_frame, ref_frame)
                            if diff > settings["diff_threshold"]:
                                ref_frame = crop_frame.copy()
                                if _stabilize_task and not _stabilize_task.done():
                                    _stabilize_task.cancel()
                                _stabilize_task = asyncio.ensure_future(_trigger_after_stabilize())
                    await asyncio.sleep(PREVIEW_INTERVAL)

            async def _ocr_task():
                nonlocal _capture_gen
                while not stop_event.is_set():
                    if settings["auto_capture"]:
                        try:
                            await asyncio.wait_for(ocr_trigger.wait(), timeout=0.5)
                            ocr_trigger.clear()
                        except asyncio.TimeoutError:
                            continue
                        _capture_gen += 1
                        this_gen = _capture_gen
                    else:
                        await asyncio.sleep(1.5)
                        if stop_event.is_set():
                            break
                        this_gen = None

                    if stop_event.is_set():
                        break

                    res = await pipeline.capture_once()

                    # Discard stale result if a newer trigger fired during OCR
                    if this_gen is not None and this_gen != _capture_gen:
                        continue

                    if res is not None:
                        text = res.get("text", "")
                        conf = res.get("confidence", 0.0)
                        engine_id = engine_manager.current_id
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        print(f"\n[{timestamp}] [{engine_id}] [Conf: {conf:.2f}] {text}")
                        if text:
                            window.set_ocr_result(text, float(conf), engine_id, timestamp)
                        if settings["auto_copy"] and text:
                            from PyQt6.QtWidgets import QApplication
                            QApplication.clipboard().setText(text)

                    await asyncio.sleep(1.5)

            preview_task = asyncio.ensure_future(_preview_task())
            ocr_task = asyncio.ensure_future(_ocr_task())
            try:
                await stop_event.wait()
            finally:
                preview_task.cancel()
                ocr_task.cancel()
                await asyncio.gather(preview_task, ocr_task, return_exceptions=True)
                window.preview_widget.stop()
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
    window_title: str | None = None
    if args.hwnd:
        hwnd = _resolve_hwnd_from_arg(args.hwnd, logging.getLogger(__name__))
    else:
        from PyQt6.QtWidgets import QDialog
        from ui.window_picker import WindowPickerDialog
        dialog = WindowPickerDialog()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            hwnd = dialog.selected_hwnd
            window_title = dialog.selected_title

    if hwnd is None:
        sys.exit("No window selected. Use --hwnd or run without it to open the picker.")

    if window_title is None:
        window_title = hex(hwnd)

    # GUI mode: create MainWindow
    if gui_mode:
        from ui.main_window import MainWindow

        window = MainWindow()
        window.set_status("—", 0.0, 0.0, window_title or hex(hwnd))
        window.show()
    else:
        window = None

    try:
        import qasync, signal
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)

        def _handle_sigint(*_):
            loop.call_soon_threadsafe(loop.stop)
        signal.signal(signal.SIGINT, _handle_sigint)

        with loop:
            try:
                loop.run_until_complete(
                    main(
                        hwnd,
                        gui_mode=gui_mode,
                        window=window,
                        window_title=window_title,
                    )
                )
            except RuntimeError as e:
                if "Event loop stopped before Future completed" not in str(e):
                    raise
    except KeyboardInterrupt:
        pass
