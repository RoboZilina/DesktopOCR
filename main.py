import argparse
import asyncio
import json
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

from core.win_utils import list_windows
from tts.manager import TTSManager
from tts.openjtalk_backend import OpenJTalkBackend
from tts.edge_tts_backend import EdgeTTSBackend

DIFF_THRESHOLD = 8.0
PREVIEW_INTERVAL = 0.25
STABILIZE_DELAY = 0.5
DEFAULT_REGION = (0, 540, 1280, 180)

DEFAULT_SETTINGS = {
    "ocr_engine": "server",
    "paddle_line_count": 3,
    "auto_capture": True,
    "auto_copy": True,
    "auto_read_selection": False,
    "auto_translate_selection": False,
    "history_visible": True,
    "text_size": "medium",
    "tray_height": "medium",
    "theme": "auto",
    "preview_visible": True,
    "ocr_canvas_visible": False,
    "vn_cleaner": True,
    "diff_threshold": 8.0,
    "dictionary_pass_enabled": True,
    "kanji_pass_enabled": False,
    # Translation settings
    "translation_enabled": True,
    "translation_backend": "auto",  # "auto" | "deepl" | "google"
    # OpenAI settings
    "openai_validator_enabled": False,
    "openai_api_key": "",
    "openai_model": "gpt-4o-mini",
    # DeepSeek settings
    "deepseek_validator_enabled": False,
    "deepseek_api_key": "",
    "deepseek_model": "deepseek-chat",
    # Google Vision settings
    "google_vision_enabled": False,
    "google_vision_api_key": "",
    # Anki integration settings
    "anki_enabled": False,
    "anki_host": "localhost",
    "anki_port": 8765,
    "anki_deck": "DesktopOCR",
    "anki_tags": "japanese, vn",
    "anki_front": "screenshot",
    "anki_back": "full_with_context",
    "anki_audio_side": "front",
    "anki_auto_translate": True,
}

SETTINGS_PATH = pathlib.Path(__file__).parent / "settings.json"


def load_settings() -> dict:
    settings = DEFAULT_SETTINGS.copy()
    if SETTINGS_PATH.exists():
        try:
            raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key in settings:
                    if key in raw:
                        settings[key] = raw[key]
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).warning("Failed to load settings: %s", exc)
    # Allow DEEPSEEK_API_KEY env var to override settings.json value
    env_key = os.environ.get("DEEPSEEK_API_KEY")
    if env_key:
        settings["deepseek_api_key"] = env_key
    if settings.get("text_size") not in ("small", "medium", "large"):
        logging.getLogger(__name__).warning("Invalid text_size '%s', resetting to 'medium'", settings.get("text_size"))
        settings["text_size"] = "medium"
    # Defensive type guards — settings.json may be hand-edited with invalid types
    if not isinstance(settings.get("anki_host"), str):
        settings["anki_host"] = "localhost"
    # bool is a subclass of int in Python — must exclude it explicitly
    if not isinstance(settings.get("anki_port"), int) or isinstance(settings.get("anki_port"), bool):
        settings["anki_port"] = 8765
    if not 1 <= settings.get("anki_port", 8765) <= 65535:
        settings["anki_port"] = 8765
    if not isinstance(settings.get("anki_deck"), str):
        settings["anki_deck"] = "DesktopOCR"
    if not isinstance(settings.get("anki_tags"), str):
        settings["anki_tags"] = "japanese, vn"
    if not isinstance(settings.get("anki_front"), str):
        settings["anki_front"] = "screenshot"
    if not isinstance(settings.get("anki_back"), str):
        settings["anki_back"] = "full_with_context"
    if not isinstance(settings.get("anki_audio_side"), str):
        settings["anki_audio_side"] = "front"
    if not isinstance(settings.get("anki_auto_translate"), bool):
        settings["anki_auto_translate"] = True
    # Boolean type guards for all remaining bool settings
    # (anki_auto_translate already guarded above)
    if not isinstance(settings.get("auto_capture"), bool):
        settings["auto_capture"] = True
    if not isinstance(settings.get("auto_copy"), bool):
        settings["auto_copy"] = True
    if not isinstance(settings.get("auto_read_selection"), bool):
        settings["auto_read_selection"] = False
    if not isinstance(settings.get("auto_translate_selection"), bool):
        settings["auto_translate_selection"] = False
    if not isinstance(settings.get("history_visible"), bool):
        settings["history_visible"] = True
    if not isinstance(settings.get("preview_visible"), bool):
        settings["preview_visible"] = True
    if not isinstance(settings.get("ocr_canvas_visible"), bool):
        settings["ocr_canvas_visible"] = False
    if not isinstance(settings.get("vn_cleaner"), bool):
        settings["vn_cleaner"] = True
    if not isinstance(settings.get("dictionary_pass_enabled"), bool):
        settings["dictionary_pass_enabled"] = True
    if not isinstance(settings.get("kanji_pass_enabled"), bool):
        settings["kanji_pass_enabled"] = False
    if not isinstance(settings.get("translation_enabled"), bool):
        settings["translation_enabled"] = True
    if not isinstance(settings.get("openai_validator_enabled"), bool):
        settings["openai_validator_enabled"] = False
    if not isinstance(settings.get("deepseek_validator_enabled"), bool):
        settings["deepseek_validator_enabled"] = False
    if not isinstance(settings.get("google_vision_enabled"), bool):
        settings["google_vision_enabled"] = False
    if not isinstance(settings.get("anki_enabled"), bool):
        settings["anki_enabled"] = False
    return settings


def save_settings(settings: dict) -> None:
    try:
        tmp = SETTINGS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        tmp.replace(SETTINGS_PATH)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("Failed to save settings: %s", exc)

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
from logic.openai_validator import OpenAIValidator
from logic.deepseek_validator import DeepSeekValidator
from logic.google_vision_ocr import GoogleVisionOCR
from logic.anki_connect import AnkiConnect
from logic.anki_card_builder import build_and_send_card



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
    parser.add_argument("--det-model", type=str, default="det.onnx", help="Detection ONNX filename")
    parser.add_argument("--rec-model", type=str, default="rec.onnx", help="Recognition ONNX filename")
    parser.add_argument("--dict-file", type=str, default="japan_dict.txt", help="Dictionary filename")
    parser.add_argument("--debug-ocr", action="store_true", help="Enable DEBUG logging for OCR engine and box filtering")
    return parser.parse_args()


def _parse_region_arg(region_arg: str) -> tuple[int, int, int, int]:
    parts = [p.strip() for p in region_arg.split(",")]
    if len(parts) != 4:
        raise ValueError("Region must have exactly 4 comma-separated integers: x,y,w,h")
    x, y, w, h = [int(v) for v in parts]
    if w <= 0 or h <= 0:
        raise ValueError("Region width and height must be > 0")
    return x, y, w, h

async def main(hwnd, gui_mode=True, window=None, window_title=""):
    args = parse_args()

    MODEL_CONFIG = {
        "det": args.det_model,
        "rec": args.rec_model,
        "dict": args.dict_file,
    }
    MODELS_DIR = args.models_dir

    if args.list_engines or args.list_engine_status:
        engine_manager = EngineManager(MODELS_DIR, MODEL_CONFIG)
        if args.list_engines:
            print("Available engines:")
            for engine_id in engine_manager.get_supported_engines():
                print("- %s" % engine_id)
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
                print("- %s: state=%s%s" % (engine_id, state, suffix))
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

    if args.debug_ocr:
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        for name in ("core.ocr_engine", "core.engine_manager"):
            dbg_logger = logging.getLogger(name)
            dbg_logger.setLevel(logging.DEBUG)
            dbg_logger.propagate = False
            handler = logging.StreamHandler()
            handler.setLevel(logging.DEBUG)
            handler.setFormatter(formatter)
            dbg_logger.handlers.clear()
            dbg_logger.addHandler(handler)

    list_windows()

    # MODEL_CONFIG and MODELS_DIR are already set up early.

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

    region_was_cli_defined = bool(args.region or args.select_region)
    selection_ready = (not gui_mode) or region_was_cli_defined

    # Apply DPI scaling to the default region so it works on non-1080p displays
    # Only applies when no explicit --region or --select-region was provided.
    try:
        import ctypes
        dpi = ctypes.windll.user32.GetDpiForSystem()
        scale = dpi / 96.0
        if selected_region is None and abs(scale - 1.0) > 0.01:
            selected_region = tuple(int(v * scale) for v in DEFAULT_REGION)
            logger.info("DPI scaling applied: %d DPI -> scale=%.2f, region=%s", dpi, scale, selected_region)
    except Exception:
        pass  # DPI detection is best-effort; fall back to unscaled default

    if selected_region is None:
        selected_region = DEFAULT_REGION
        logger.info("Using default region: %s", selected_region)

    capture.set_region(*selected_region)
  
    
    settings_state = load_settings()
    try:
        saved_line_count = max(1, min(5, int(settings_state.get("paddle_line_count", 3) or 3)))
    except (ValueError, TypeError):
        saved_line_count = 3
    google_vision: GoogleVisionOCR | None = None

    def _set_status_message(status_text: str, summary_text: str) -> None:
        if gui_mode and window is not None:
            window.set_status(status_text, summary_text)

    # Validators must be constructed empty and configured exclusively via update_settings()
    # to ensure startup restore, reset, and UI toggles all follow the same code path.
    openai_validator = OpenAIValidator("")
    openai_validator.update_settings(
        api_key=settings_state.get("openai_api_key", ""),
        enabled=settings_state.get("openai_validator_enabled", False),
        model=settings_state.get("openai_model", "gpt-4o-mini"),
    )

    deepseek_validator = DeepSeekValidator()
    deepseek_validator.update_settings(
        api_key=settings_state.get("deepseek_api_key", ""),
        enabled=settings_state.get("deepseek_validator_enabled", False),
        model=settings_state.get("deepseek_model", "deepseek-chat"),
    )

    google_vision = GoogleVisionOCR()
    google_vision.update_settings(
        api_key=settings_state.get("google_vision_api_key", ""),
        enabled=settings_state.get("google_vision_enabled", False),
    )
    google_vision.set_status_callback(_set_status_message)
    
    pipeline = CapturePipeline(
        engine_manager,
        capture,
        openai_validator,
        google_vision,
        deepseek_validator,
    )
    pipeline.set_line_count(saved_line_count)

    def _persist_line_count(value: int) -> None:
        nonlocal saved_line_count
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            normalized = 3
        normalized = max(1, min(5, normalized))
        pipeline.set_line_count(normalized)
        if normalized == saved_line_count:
            return
        saved_line_count = normalized
        settings_state["paddle_line_count"] = normalized
        save_settings(settings_state)

    def _selected_line_count() -> int:
        if gui_mode and window is not None and hasattr(window, "get_active_line_count"):
            try:
                return int(window.get_active_line_count())
            except Exception:  # noqa: BLE001
                return saved_line_count
        return saved_line_count

    try:
        if gui_mode and window is not None:
            window.set_status("Loading engine…", "")
        logger.info("Loading engine: %s ...", args.engine)
        success = await engine_manager.switch_engine(args.engine)
        if not success:
            logger.error("Failed to load engine: %s", args.engine)
            return
        if gui_mode and window is not None:
            window.set_status("Ready", "")

        # ---- GUI controls setup -----------------------------------
        if gui_mode:
            async def _on_engine_changed(engine_id: str):
                if window is not None:
                    window.set_status("Loading engine…", "")
                ok = await engine_manager.switch_engine(engine_id)
                if ok and window is not None:
                    window.set_status("Ready", "")

            window.engine_changed.connect(
                lambda eid: asyncio.create_task(_on_engine_changed(eid))
            )

            if hasattr(window, "set_active_engine"):
                if args.engine.startswith("paddle"):
                    window.set_active_engine("paddle", line_count=saved_line_count)
                else:
                    window.set_active_engine(args.engine)

            if hasattr(window, "paddle_line_count_changed"):
                window.paddle_line_count_changed.connect(_persist_line_count)

            # Translation is handled by MainWindow._on_translate_requested
            # (wired in MainWindow.__init__) — no stub needed here.

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
                raw = await engine_manager.run_ocr(frame, line_count=_selected_line_count())
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

            streaming_enabled = True

            def _handle_stop_stream():
                nonlocal streaming_enabled, capture, ref_frame
                if not streaming_enabled:
                    return
                streaming_enabled = False
                ref_frame = None
                capture.stop()
                window.clear_preview("Stream paused — select a source window to resume.")
                window.controls_bar.set_streaming(False)
                window.set_status("Ready", "")

            def _handle_select_window():
                nonlocal streaming_enabled, capture, hwnd, window_title, ref_frame
                from PyQt6.QtWidgets import QDialog
                from ui.window_picker import WindowPickerDialog

                window.controls_bar.set_streaming(False)
                streaming_enabled = False
                window.clear_preview("Select a source window to start streaming.", clear_selection=True)

                dialog = WindowPickerDialog(window)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    window.controls_bar.set_streaming(False)
                    return

                new_hwnd = dialog.selected_hwnd
                new_title = dialog.selected_title or hex(new_hwnd)
                old_region = capture.region
                capture.stop()
                capture = ScreenCapture(new_hwnd)
                if old_region:
                    capture.set_region(*old_region)
                pipeline.capture = capture
                hwnd = new_hwnd
                window_title = new_title
                streaming_enabled = True
                ref_frame = None
                window.controls_bar.set_streaming(True)
                window.request_preview_auto_fit()
                window.set_status("Ready", "")
                ocr_trigger.set()

            window.stop_stream_requested.connect(_handle_stop_stream)
            window.select_window_requested.connect(_handle_select_window)

            # Connect overlay selection to capture region updates
            def _on_region_changed(nx, ny, nw, nh):
                nonlocal ref_frame, _capture_gen, selection_ready
                imgW, imgH = window.preview_widget.frame_size
                if imgW == 0 or imgH == 0:
                    return
                x = int(nx * imgW)
                y = int(ny * imgH)
                w = int(nw * imgW)
                h = int(nh * imgH)
                capture.set_region(x, y, w, h)
                capture._last_full_hash = None
                capture._last_crop_hash = None
                logger.info("Region selected: x=%d y=%d w=%d h=%d", x, y, w, h)
                ref_frame = None
                pipeline.invalidate_generation()
                _capture_gen += 1
                selection_ready = True
                ocr_trigger.clear()

            window.preview_widget.selection_overlay.region_changed.connect(_on_region_changed)

            # Wire side menu toggles — all persist to settings_state on disk
            _save_blocked = False
            def _do_save():
                if not _save_blocked:
                    save_settings(settings_state)

            def _on_auto_capture_changed(enabled: bool):
                settings_state["auto_capture"] = enabled
                _do_save()
            window.side_menu.auto_capture_changed.connect(_on_auto_capture_changed)

            def _on_auto_copy_changed(enabled: bool):
                settings_state["auto_copy"] = enabled
                window.set_auto_copy(enabled)
                _do_save()
            window.side_menu.auto_copy_changed.connect(_on_auto_copy_changed)

            def _on_auto_read_selection_changed(enabled: bool):
                settings_state["auto_read_selection"] = enabled
                _do_save()
            window.side_menu.auto_read_selection_changed.connect(_on_auto_read_selection_changed)

            def _on_history_visible_changed(visible: bool):
                settings_state["history_visible"] = visible
                window.history_sidebar.setVisible(visible)
                _do_save()
            window.side_menu.history_visible_changed.connect(_on_history_visible_changed)

            def _on_preview_visible_changed(enabled: bool):
                settings_state["preview_visible"] = enabled
                window.preview_widget.setVisible(enabled)
                _do_save()
            window.side_menu.preview_visible_changed.connect(_on_preview_visible_changed)

            def _on_text_size_changed(size_id: str):
                settings_state["text_size"] = size_id
                _do_save()
            window.side_menu.text_size_changed.connect(_on_text_size_changed)
            window.side_menu.text_size_changed.connect(window.transcription_tray.set_text_size)

            def _on_tray_height_changed(size_id: str):
                settings_state["tray_height"] = size_id
                _do_save()
            window.side_menu.tray_height_changed.connect(_on_tray_height_changed)
            window.side_menu.tray_height_changed.connect(window.transcription_tray.set_tray_height)

            def _on_theme_changed(theme_id: str):
                settings_state["theme"] = theme_id
                _do_save()
            window.side_menu.theme_changed.connect(_on_theme_changed)

            def _on_auto_translate_selection_changed(enabled: bool):
                settings_state["auto_translate_selection"] = enabled
                _do_save()
            window.side_menu.auto_translate_selection_changed.connect(_on_auto_translate_selection_changed)

            def _on_translation_enabled_changed(enabled: bool):
                settings_state["translation_enabled"] = enabled
                window._on_translation_enabled_changed(enabled)
                _do_save()
            window.side_menu.translation_enabled_changed.connect(_on_translation_enabled_changed)

            def _on_translation_backend_changed(backend_id: str):
                settings_state["translation_backend"] = backend_id
                window._on_translation_backend_changed(backend_id)
                _do_save()
            window.side_menu.translation_backend_changed.connect(_on_translation_backend_changed)

            def _on_vn_cleaner_changed(enabled: bool):
                settings_state["vn_cleaner"] = enabled
                if enabled:
                    os.environ.pop("DESKTOCR_DISABLE_VALIDATOR", None)
                else:
                    os.environ["DESKTOCR_DISABLE_VALIDATOR"] = "1"
                _do_save()
            window.side_menu.vn_cleaner_changed.connect(_on_vn_cleaner_changed)

            def _on_ocr_canvas_visible_changed(enabled: bool):
                settings_state["ocr_canvas_visible"] = enabled
                window._on_ocr_canvas_visible_changed(enabled)
                _do_save()
            window.side_menu.ocr_canvas_visible_changed.connect(_on_ocr_canvas_visible_changed)

            def _on_diff_threshold_changed(value: float):
                settings_state["diff_threshold"] = value
                _do_save()
            window.side_menu.diff_threshold_changed.connect(_on_diff_threshold_changed)

            def _on_dictionary_pass_changed(enabled: bool):
                settings_state["dictionary_pass_enabled"] = enabled
                window.transcription_tray.set_enable_dictionary_pass(enabled)
                _do_save()

            window.side_menu.dictionary_pass_changed.connect(_on_dictionary_pass_changed)

            def _on_kanji_pass_changed(enabled: bool):
                settings_state["kanji_pass_enabled"] = enabled
                window.transcription_tray.set_enable_kanji_pass(enabled)
                _do_save()

            window.side_menu.kanji_pass_changed.connect(_on_kanji_pass_changed)

            # OpenAI Validator Settings
            def _on_openai_enabled_changed(enabled: bool):
                settings_state["openai_validator_enabled"] = enabled
                openai_validator.update_settings(enabled=enabled)
                _do_save()

            window.side_menu.openai_validator_enabled_changed.connect(
                _on_openai_enabled_changed
            )
            def _on_openai_api_key_changed(key: str):
                settings_state["openai_api_key"] = key
                openai_validator.update_settings(api_key=key)
                _do_save()
                _set_status_message("Ready", "OpenAI key updated")
            window.side_menu.openai_api_key_changed.connect(_on_openai_api_key_changed)
            def _on_openai_model_changed(model: str):
                settings_state["openai_model"] = model
                openai_validator.update_settings(model=model)
                _do_save()
            window.side_menu.openai_model_changed.connect(_on_openai_model_changed)

            def _on_deepseek_enabled_changed(enabled: bool):
                settings_state["deepseek_validator_enabled"] = enabled
                deepseek_validator.update_settings(enabled=enabled)
                _do_save()

            def _on_deepseek_api_key_changed(key: str):
                settings_state["deepseek_api_key"] = key
                deepseek_validator.update_settings(api_key=key)
                _do_save()
                _set_status_message("Ready", "DeepSeek key updated")

            def _on_deepseek_model_changed(model: str):
                settings_state["deepseek_model"] = model
                deepseek_validator.update_settings(model=model)
                _do_save()

            window.side_menu.deepseek_validator_enabled_changed.connect(_on_deepseek_enabled_changed)
            window.side_menu.deepseek_api_key_changed.connect(_on_deepseek_api_key_changed)
            window.side_menu.deepseek_model_changed.connect(_on_deepseek_model_changed)

            def _on_google_vision_enabled_changed(enabled: bool):
                settings_state["google_vision_enabled"] = enabled
                google_vision.update_settings(enabled=enabled)
                _do_save()

            def _on_google_vision_key_changed(key: str):
                settings_state["google_vision_api_key"] = key
                google_vision.update_settings(api_key=key)
                _do_save()
                _set_status_message("Ready", "Google Vision key updated")

            window.side_menu.google_vision_enabled_changed.connect(_on_google_vision_enabled_changed)
            window.side_menu.google_vision_api_key_changed.connect(_on_google_vision_key_changed)

            # --- Startup UI restoration (no signals to avoid save storms) ---
            window.transcription_tray.set_enable_dictionary_pass(
                settings_state.get("dictionary_pass_enabled", True)
            )
            window.transcription_tray.set_enable_kanji_pass(
                settings_state.get("kanji_pass_enabled", False)
            )
            # Restore side menu toggles without emitting signals
            window.side_menu.set_auto_read_selection(
                settings_state.get("auto_read_selection", False), emit_signal=False
            )
            if hasattr(window.side_menu, "set_translation_enabled"):
                window.side_menu.set_translation_enabled(
                    settings_state.get("translation_enabled", True), emit_signal=False
                )
            window.side_menu.set_auto_translate_selection(
                settings_state.get("auto_translate_selection", False), emit_signal=False
            )
            window.side_menu.set_enable_dictionary_pass(
                settings_state.get("dictionary_pass_enabled", True), emit_signal=False
            )
            window.side_menu.set_enable_kanji_pass(
                settings_state.get("kanji_pass_enabled", False), emit_signal=False
            )
            window.side_menu.set_auto_capture(
                settings_state.get("auto_capture", True), emit_signal=False
            )
            window.side_menu.set_auto_copy(
                settings_state.get("auto_copy", True), emit_signal=False
            )
            if hasattr(window, "set_auto_copy"):
                window.set_auto_copy(settings_state.get("auto_copy", True))
            if hasattr(window.side_menu, "set_preview_visible"):
                window.side_menu.set_preview_visible(
                    settings_state.get("preview_visible", True), emit_signal=False
                )
            if hasattr(window.side_menu, "set_ocr_canvas_visible"):
                window.side_menu.set_ocr_canvas_visible(
                    settings_state.get("ocr_canvas_visible", False), emit_signal=False
                )
            window.side_menu.set_openai_validator_enabled(
                settings_state.get("openai_validator_enabled", False), emit_signal=False
            )
            window.side_menu.set_openai_api_key(settings_state.get("openai_api_key", ""))
            window.side_menu.set_openai_model(settings_state.get("openai_model", "gpt-4o-mini"))
            window.side_menu.set_deepseek_validator_enabled(
                settings_state.get("deepseek_validator_enabled", False), emit_signal=False
            )
            window.side_menu.set_deepseek_api_key(settings_state.get("deepseek_api_key", ""))
            window.side_menu.set_deepseek_model(settings_state.get("deepseek_model", "deepseek-chat"))
            window.side_menu.set_google_vision_enabled(
                settings_state.get("google_vision_enabled", False), emit_signal=False
            )
            window.side_menu.set_google_vision_api_key(settings_state.get("google_vision_api_key", ""))
            if hasattr(window.side_menu, "set_history_visible"):
                window.side_menu.set_history_visible(
                    settings_state.get("history_visible", True), emit_signal=False
                )
            window.history_sidebar.setVisible(
                settings_state.get("history_visible", True)
            )
            # Theme, text size, tray height
            if hasattr(window.side_menu, "set_theme_id"):
                window.side_menu.set_theme_id(
                    settings_state.get("theme", "auto"), emit_signal=False
                )
            if hasattr(window.side_menu, "set_text_size"):
                window.side_menu.set_text_size(
                    settings_state.get("text_size", "medium"), emit_signal=False
                )
            if hasattr(window.side_menu, "set_tray_height"):
                window.side_menu.set_tray_height(
                    settings_state.get("tray_height", "medium"), emit_signal=False
                )
            if hasattr(window.side_menu, "set_diff_threshold"):
                window.side_menu.set_diff_threshold(
                    settings_state.get("diff_threshold", 8.0), emit_signal=False
                )
            # Apply side effects that signal handlers normally perform
            window.preview_widget.setVisible(
                settings_state.get("preview_visible", True)
            )
            window._on_ocr_canvas_visible_changed(
                settings_state.get("ocr_canvas_visible", False)
            )
            window._on_auto_read_selection_changed(
                settings_state.get("auto_read_selection", False)
            )
            window._on_auto_translate_selection_changed(
                settings_state.get("auto_translate_selection", False)
            )
            window._on_translation_enabled_changed(
                settings_state.get("translation_enabled", True)
            )
            if hasattr(window.side_menu, "set_translation_backend"):
                window.side_menu.set_translation_backend(
                    settings_state.get("translation_backend", "auto"), emit_signal=False
                )
            window._on_translation_backend_changed(
                settings_state.get("translation_backend", "auto")
            )
            if hasattr(window.side_menu, "set_vn_cleaner"):
                window.side_menu.set_vn_cleaner(
                    settings_state.get("vn_cleaner", True), emit_signal=False
                )
            _on_vn_cleaner_changed(settings_state.get("vn_cleaner", True))
            # Apply theme side effect
            theme_id = settings_state.get("theme", "auto")
            if theme_id != "auto":
                window._apply_theme(theme_id)
            # Apply text size / tray height side effects
            window.transcription_tray.set_text_size(
                settings_state.get("text_size", "medium")
            )
            window.transcription_tray.set_tray_height(
                settings_state.get("tray_height", "medium")
            )

            # Restore Anki settings (no signals)
            if hasattr(window.side_menu, "set_anki_enabled"):
                window.side_menu.set_anki_enabled(
                    settings_state.get("anki_enabled", False), emit_signal=False
                )
            window.set_anki_visible(settings_state.get("anki_enabled", False))
            if hasattr(window.side_menu, "set_anki_host"):
                window.side_menu.set_anki_host(settings_state.get("anki_host", "localhost"))
            if hasattr(window.side_menu, "set_anki_port"):
                window.side_menu.set_anki_port(settings_state.get("anki_port", 8765))
            if hasattr(window.side_menu, "set_anki_deck"):
                window.side_menu.set_anki_deck(settings_state.get("anki_deck", "DesktopOCR"))
            if hasattr(window.side_menu, "set_anki_tags"):
                window.side_menu.set_anki_tags(settings_state.get("anki_tags", "japanese, vn"))
            if hasattr(window.side_menu, "set_anki_front"):
                window.side_menu.set_anki_front(settings_state.get("anki_front", "screenshot"))
            if hasattr(window.side_menu, "set_anki_back"):
                window.side_menu.set_anki_back(settings_state.get("anki_back", "full_with_context"))
            if hasattr(window.side_menu, "set_anki_audio_side"):
                window.side_menu.set_anki_audio_side(settings_state.get("anki_audio_side", "front"))
            if hasattr(window.side_menu, "set_anki_auto_translate"):
                window.side_menu.set_anki_auto_translate(
                    settings_state.get("anki_auto_translate", True), emit_signal=False
                )

            # --- Reset ---
            def _apply_defaults_to_ui(window, *, emit_signals: bool) -> None:
                # Read only from DEFAULT_SETTINGS
                defaults = DEFAULT_SETTINGS
                es = emit_signals

                # Side menu toggles
                window.side_menu.set_auto_capture(defaults.get("auto_capture", True), emit_signal=es)
                window.side_menu.set_auto_copy(defaults.get("auto_copy", True), emit_signal=es)
                if hasattr(window.side_menu, "set_auto_read_selection"):
                    window.side_menu.set_auto_read_selection(defaults.get("auto_read_selection", False), emit_signal=es)
                if hasattr(window.side_menu, "set_auto_translate_selection"):
                    window.side_menu.set_auto_translate_selection(defaults.get("auto_translate_selection", False), emit_signal=es)

                # Text highlights / passes
                if hasattr(window.side_menu, "set_enable_dictionary_pass"):
                    window.side_menu.set_enable_dictionary_pass(defaults.get("dictionary_pass_enabled", True), emit_signal=es)
                if hasattr(window.side_menu, "set_enable_kanji_pass"):
                    window.side_menu.set_enable_kanji_pass(defaults.get("kanji_pass_enabled", False), emit_signal=es)

                # Translation
                if hasattr(window.side_menu, "set_translation_enabled"):
                    window.side_menu.set_translation_enabled(defaults.get("translation_enabled", False), emit_signal=es)
                if hasattr(window.side_menu, "set_translation_backend"):
                    window.side_menu.set_translation_backend(defaults.get("translation_backend", "auto"), emit_signal=es)

                # Validators
                window.side_menu.set_openai_validator_enabled(defaults.get("openai_validator_enabled", False), emit_signal=es)
                window.side_menu.set_openai_api_key(defaults.get("openai_api_key", ""))
                window.side_menu.set_openai_model(defaults.get("openai_model", "gpt-4o-mini"))
                window.side_menu.set_deepseek_validator_enabled(defaults.get("deepseek_validator_enabled", False), emit_signal=es)
                window.side_menu.set_deepseek_api_key(defaults.get("deepseek_api_key", ""))
                window.side_menu.set_deepseek_model(defaults.get("deepseek_model", "deepseek-chat"))
                window.side_menu.set_google_vision_enabled(defaults.get("google_vision_enabled", False), emit_signal=es)
                window.side_menu.set_google_vision_api_key(defaults.get("google_vision_api_key", ""))

                # VN cleaner
                if hasattr(window.side_menu, "set_vn_cleaner"):
                    window.side_menu.set_vn_cleaner(defaults.get("vn_cleaner", True), emit_signal=es)

                # Visual toggles
                if hasattr(window.side_menu, "set_preview_visible"):
                    window.side_menu.set_preview_visible(defaults.get("preview_visible", True), emit_signal=es)
                if hasattr(window.side_menu, "set_ocr_canvas_visible"):
                    window.side_menu.set_ocr_canvas_visible(defaults.get("ocr_canvas_visible", False), emit_signal=es)
                if hasattr(window.side_menu, "set_history_visible"):
                    window.side_menu.set_history_visible(defaults.get("history_visible", True), emit_signal=es)

                # Theme / text size / tray height
                if hasattr(window.side_menu, "set_theme_id"):
                    window.side_menu.set_theme_id(defaults.get("theme", "auto"), emit_signal=es)
                if hasattr(window.side_menu, "set_text_size"):
                    window.side_menu.set_text_size(defaults.get("text_size", "medium"), emit_signal=es)
                if hasattr(window.side_menu, "set_tray_height"):
                    window.side_menu.set_tray_height(defaults.get("tray_height", "medium"), emit_signal=es)

                # Diff threshold
                if hasattr(window.side_menu, "set_diff_threshold"):
                    window.side_menu.set_diff_threshold(defaults.get("diff_threshold", 8.0), emit_signal=es)

                # Anki settings
                if hasattr(window.side_menu, "set_anki_enabled"):
                    window.side_menu.set_anki_enabled(defaults.get("anki_enabled", False), emit_signal=es)
                if hasattr(window.side_menu, "set_anki_host"):
                    window.side_menu.set_anki_host(defaults.get("anki_host", "localhost"))
                if hasattr(window.side_menu, "set_anki_port"):
                    window.side_menu.set_anki_port(defaults.get("anki_port", 8765))
                if hasattr(window.side_menu, "set_anki_deck"):
                    window.side_menu.set_anki_deck(defaults.get("anki_deck", "DesktopOCR"))
                if hasattr(window.side_menu, "set_anki_tags"):
                    window.side_menu.set_anki_tags(defaults.get("anki_tags", "japanese, vn"))
                if hasattr(window.side_menu, "set_anki_front"):
                    window.side_menu.set_anki_front(defaults.get("anki_front", "screenshot"))
                if hasattr(window.side_menu, "set_anki_back"):
                    window.side_menu.set_anki_back(defaults.get("anki_back", "full_with_context"))
                if hasattr(window.side_menu, "set_anki_audio_side"):
                    window.side_menu.set_anki_audio_side(defaults.get("anki_audio_side", "front"))
                if hasattr(window.side_menu, "set_anki_auto_translate"):
                    window.side_menu.set_anki_auto_translate(defaults.get("anki_auto_translate", True), emit_signal=es)

                # Apply non-side-menu visual state directly to widgets
                window.preview_widget.setVisible(defaults.get("preview_visible", True))
                window._on_ocr_canvas_visible_changed(defaults.get("ocr_canvas_visible", False))
                window.history_sidebar.setVisible(defaults.get("history_visible", True))

                # Apply theme side effect
                window._apply_theme(defaults.get("theme", "auto"))

                # Apply vn_cleaner env-var side effect
                _on_vn_cleaner_changed(defaults.get("vn_cleaner", True))

            def _on_reset_requested() -> None:
                nonlocal _save_blocked
                _save_blocked = True
                try:
                    # Apply defaults to UI and emit signals so handlers update settings_state
                    _apply_defaults_to_ui(window, emit_signals=True)
                finally:
                    _save_blocked = False

                # Persist the final state once
                _do_save()

            window.side_menu.reset_requested.connect(_on_reset_requested)

            # TTS manager (Edge TTS active, OpenJTalk fallback)
            tts = TTSManager([
                EdgeTTSBackend(),
                OpenJTalkBackend(),
            ])
            window.tts_requested.connect(tts.speak)

            # ---- Anki integration ----------------------------------------
            anki = AnkiConnect(
                host=settings_state.get("anki_host", "localhost"),
                port=settings_state.get("anki_port", 8765),
            )

            _anki_busy = False

            async def _check_anki() -> None:
                """Poll AnkiConnect availability every 30 s and update the tray button."""
                if not settings_state.get("anki_enabled", False):
                    return
                available = await anki.is_available()
                if available:
                    ok = await anki.ensure_note_type()
                    if not ok:
                        # Note type creation failed — show button as unavailable
                        # so the user sees the error message in the tooltip.
                        available = False
                if window is not None:
                    window.set_anki_available(available, anki.last_error)

            async def _on_anki_requested() -> None:
                """Build and send an Anki card from the current OCR state."""
                nonlocal _anki_busy
                if window is None or _anki_busy:
                    return
                _anki_busy = True
                try:
                    ocr_text = window.get_ocr_text()
                    selection_text = window.get_selection_text()
                    # Don't use the UI translation box — it shows the selection
                    # translation, not the OCR translation. Always translate fresh
                    # for the Anki card to ensure correct text/translation pairs.
                    cached_translation = None

                    # Fire translations for both texts concurrently (silent, for Anki only)
                    async def _translate(text: str) -> str | None:
                        if not text or not text.strip():
                            return None
                        if not getattr(window, "_translation_enabled", True):
                            return None
                        try:
                            return await window.get_translation_manager().translate(text)
                        except Exception:
                            return None

                    # Translate sequentially — TranslationManager uses a per-call lock
                    # that silently skips concurrent requests (returns "").
                    # Sequential translation avoids lock contention and ensures both
                    # texts are properly translated.
                    ocr_translation = cached_translation or None
                    selection_translation = None
                    if settings_state.get("anki_auto_translate", True):
                        if not ocr_translation:
                            ocr_result = await _translate(ocr_text)
                            ocr_translation = ocr_result or None
                        if selection_text and selection_text.strip():
                            sel_result = await _translate(selection_text)
                            selection_translation = sel_result or None

                    # Auto-generate TTS audio for the card.
                    # Always generate for target_text (selection -> OCR fallback).
                    # When back template is full_with_context and selection differs
                    # from OCR, also generate for the full OCR context text.
                    audio_paths: list[str] = []
                    tts_backend = getattr(tts, "active", None)
                    target_text_for_tts = (selection_text or "").strip() or (ocr_text or "").strip()

                    if target_text_for_tts and hasattr(tts_backend, "generate"):
                        path = await tts_backend.generate(target_text_for_tts)
                        if path:
                            audio_paths.append(path)

                    back_mode = settings_state.get("anki_back", "full_with_context")
                    needs_context_audio = (
                        back_mode == "full_with_context"
                        and selection_text
                        and selection_text.strip()
                        and ocr_text
                        and ocr_text.strip()
                        and ocr_text.strip() != target_text_for_tts
                    )
                    if needs_context_audio and hasattr(tts_backend, "generate"):
                        path = await tts_backend.generate(ocr_text)
                        if path:
                            audio_paths.append(path)

                    logger.info(
                        "[Anki] _on_anki_requested: calling build_and_send_card with "
                        "ocr_text='%s' (len=%d), selection_text='%s' (len=%d), "
                        "ocr_translation='%s' (len=%d), selection_translation='%s' (len=%d), "
                        "anki_auto_translate=%r, audio_paths=%s",
                        ocr_text[:60] if ocr_text else "(empty)",
                        len(ocr_text or ""),
                        selection_text[:60] if selection_text else "(empty)",
                        len(selection_text or ""),
                        ocr_translation[:60] if ocr_translation else "(empty)",
                        len(ocr_translation or ""),
                        selection_translation[:60] if selection_translation else "(empty)",
                        len(selection_translation or ""),
                        settings_state.get("anki_auto_translate", True),
                        audio_paths or "(none)",
                    )
                    ok = await build_and_send_card(
                        anki, capture,
                        ocr_text, selection_text,
                        ocr_translation, selection_translation,
                        audio_paths,
                        settings_state,
                    )
                    if ok and window is not None:
                        window.set_status("Done", "Anki card saved ✓")
                    elif window is not None:
                        reason = anki.last_error or "Card save failed"
                        window.set_status("Error", f"Anki: {reason}")
                    # StatusBar auto-clears "Done"/"Error" natively — no manual timer needed.
                finally:
                    _anki_busy = False

            # Wire Anki button
            window.anki_requested.connect(
                lambda: _safe_task(_on_anki_requested())
            )

            # Periodic availability check
            from PyQt6.QtCore import QTimer
            _anki_tasks: set[asyncio.Task] = set()

            def _safe_check_anki() -> None:
                """Create _check_anki task and track it for GC hygiene."""
                task = asyncio.create_task(_check_anki())
                _anki_tasks.add(task)
                task.add_done_callback(_anki_tasks.discard)

            def _safe_task(coro) -> None:
                """Create and track a one-off async task."""
                task = asyncio.create_task(coro)
                _anki_tasks.add(task)
                task.add_done_callback(_anki_tasks.discard)

            window._anki_timer = QTimer(window)
            window._anki_timer.timeout.connect(_safe_check_anki)
            window._anki_timer.start(30_000)
            # Also fire once immediately on startup
            _safe_check_anki()

            # Wire side menu Anki signals
            def _on_anki_enabled_changed(enabled: bool):
                settings_state["anki_enabled"] = enabled
                window.set_anki_visible(enabled)
                if enabled:
                    anki._clear_error()
                    _safe_check_anki()
                _do_save()
            window.side_menu.anki_enabled_changed.connect(_on_anki_enabled_changed)

            def _on_anki_host_changed(host: str):
                settings_state["anki_host"] = host
                anki.set_host_port(host, settings_state.get("anki_port", 8765))
                anki._clear_error()
                _safe_check_anki()
                _do_save()
            window.side_menu.anki_host_changed.connect(_on_anki_host_changed)

            def _on_anki_port_changed(port: int):
                settings_state["anki_port"] = port
                host = settings_state.get("anki_host", "localhost")
                anki.set_host_port(host, port)
                anki._clear_error()
                _safe_check_anki()
                _do_save()
            window.side_menu.anki_port_changed.connect(_on_anki_port_changed)

            def _on_anki_deck_changed(deck: str):
                settings_state["anki_deck"] = deck
                _do_save()
            window.side_menu.anki_deck_changed.connect(_on_anki_deck_changed)

            def _on_anki_tags_changed(tags: str):
                settings_state["anki_tags"] = tags
                _do_save()
            window.side_menu.anki_tags_changed.connect(_on_anki_tags_changed)

            def _on_anki_front_changed(mode: str):
                settings_state["anki_front"] = mode
                _do_save()
            window.side_menu.anki_front_changed.connect(_on_anki_front_changed)

            def _on_anki_back_changed(mode: str):
                settings_state["anki_back"] = mode
                _do_save()
            window.side_menu.anki_back_changed.connect(_on_anki_back_changed)

            def _on_anki_audio_side_changed(side: str):
                settings_state["anki_audio_side"] = side
                _do_save()
            window.side_menu.anki_audio_side_changed.connect(_on_anki_audio_side_changed)

            def _on_anki_auto_translate_changed(enabled: bool):
                settings_state["anki_auto_translate"] = enabled
                _do_save()
            window.side_menu.anki_auto_translate_changed.connect(_on_anki_auto_translate_changed)

            # Test Connection button
            async def _on_anki_test_requested() -> None:
                if window is None:
                    return
                available = await anki.is_available()
                if available:
                    window.set_status("Done", "AnkiConnect OK ✓")
                else:
                    reason = anki.last_error or f"Cannot reach Anki at {anki.base_url}"
                    window.set_status("Error", reason)
                # StatusBar auto-clears "Done"/"Error" natively — no manual timer needed.
            window.side_menu.anki_test_requested.connect(
                lambda: _safe_task(_on_anki_test_requested())
            )

            # Populate voice selector from TTS backend
            voices = tts.list_voices()
            window.controls_bar.load_voices(voices)
            window.controls_bar.voice_changed.connect(lambda vid: tts.set_voice(vid))

            ocr_trigger = asyncio.Event()

            def _build_status_summary(meta: dict | None = None, *, conf: float = 0.0, elapsed_ms: float = 0.0) -> str:
                meta = meta or {}
                active_window = window_title or "—"
                engine_label = meta.get("engine", engine_manager.current_id)
                translator_label = window.get_translator_summary()
                validator_meta = meta.get("ai_validator") or meta.get("validator") or {}
                validator_name = validator_meta.get("engine")
                if not validator_name:
                    enabled_flag = validator_meta.get("enabled")
                    if enabled_flag is None:
                        validator_name = "deterministic"
                    else:
                        validator_name = "On" if enabled_flag else "Off"
                tts_name = getattr(getattr(tts, "active", None), "name", "default")
                summary = (
                    f"Window: {active_window} | "
                    f"Engine: {engine_label} | "
                    f"Translator: {translator_label} | "
                    f"Validator: {validator_name} | "
                    f"TTS: {tts_name}"
                )
                if os.getenv("DESKTOCR_DEBUG_UI") == "1":
                    boxes = int(meta.get("boxes_raw", 0) or 0)
                    expanded_flag = os.getenv("DESKTOCR_PADDLE_EXPAND", "1") == "1"
                    summary += (
                        f" | Boxes: {boxes}"
                        f" | Confidence: {conf:.2f}"
                        f" | Expanded: {'yes' if expanded_flag else 'no'}"
                        f" | Time: {elapsed_ms:.1f} ms"
                    )
                return summary

            # Wire re-capture button in tray to force immediate OCR
            def _on_recapture():
                nonlocal _capture_gen
                if hwnd is None:
                    QMessageBox.warning(window, "No area selected",
                                        "Please select a source window first.")
                    return
                logger.info("[Recapture] Button clicked — bumping gen to %d, invalidating pipeline, firing trigger",
                            _capture_gen + 1)
                # Bump generation to invalidate any in-flight OCR result,
                # forcing a fresh capture once the current one finishes.
                _capture_gen += 1
                pipeline.invalidate_generation()  # short-circuit in-flight capture_once
                ocr_trigger.set()
            window.recapture_requested.connect(_on_recapture)
            ref_frame: np.ndarray | None = None
            _capture_gen = 0  # incremented on each OCR trigger; stale results discarded

            async def _preview_task():
                nonlocal ref_frame
                _stabilize_task: asyncio.Task | None = None

                async def _trigger_after_stabilize():
                    await asyncio.sleep(STABILIZE_DELAY)
                    ocr_trigger.set()

                while not stop_event.is_set():
                    if not streaming_enabled:
                        await asyncio.sleep(PREVIEW_INTERVAL)
                        continue
                    full_frame = await capture.get_frame(full=True)
                    if full_frame is not None:
                        if capture.last_frame is None:
                            logger.debug("[Preview] Got full frame but _last_frame is still None! shape=%s", full_frame.shape)
                        window.set_preview_frame(full_frame)
                        # New frame arrived — restart stabilize timer
                        if settings_state["auto_capture"] and selection_ready:
                            if _stabilize_task and not _stabilize_task.done():
                                _stabilize_task.cancel()
                            _stabilize_task = asyncio.create_task(_trigger_after_stabilize())
                    else:
                        # Identical frame (MD5 match) — ensure a stabilize task is pending
                        # so auto-capture keeps working on static content.
                        if settings_state["auto_capture"] and selection_ready:
                            if _stabilize_task is None or _stabilize_task.done():
                                _stabilize_task = asyncio.create_task(_trigger_after_stabilize())
                    await asyncio.sleep(PREVIEW_INTERVAL)

            async def _ocr_task():
                nonlocal _capture_gen
                while not stop_event.is_set():
                    try:
                        if not streaming_enabled:
                            await asyncio.sleep(0.5)
                            continue
                        if not selection_ready:
                            await asyncio.sleep(0.2)
                            continue
                        if settings_state["auto_capture"]:
                            try:
                                await asyncio.wait_for(ocr_trigger.wait(), timeout=0.5)
                                ocr_trigger.clear()
                            except asyncio.TimeoutError:
                                continue
                            _capture_gen += 1
                            this_gen = _capture_gen
                            logger.info("[OCR] Auto trigger consumed (gen=%d)", this_gen)
                        else:
                            # Manual mode: wait for Re-capture button only
                            try:
                                await asyncio.wait_for(ocr_trigger.wait(), timeout=1.5)
                                ocr_trigger.clear()
                            except asyncio.TimeoutError:
                                continue
                            this_gen = None
                            logger.info("[OCR] Manual trigger consumed (re-capture)")

                        if stop_event.is_set():
                            break

                        # No "Processing…" status needed — the user knows they
                        # triggered a recapture; we'll show "Done" with summary
                        # when results arrive.
                        ocr_started = time.perf_counter()
                        res = await pipeline.capture_once(line_count=_selected_line_count())
                        elapsed_ms = (time.perf_counter() - ocr_started) * 1000.0

                        # Discard stale result if a newer trigger fired during OCR
                        if this_gen is not None and this_gen != _capture_gen:
                            logger.info("[OCR] Stale result discarded (this_gen=%d, current_gen=%d)",
                                        this_gen, _capture_gen)
                            continue

                        if res is not None:
                            text = res.get("text", "")
                            conf = res.get("confidence", 0.0)
                            meta = res.get("meta", {}) if isinstance(res, dict) else {}
                            preprocessed_frame = res.get("preprocessed_frame") if isinstance(res, dict) else None
                            raw_frame = res.get("frame") if isinstance(res, dict) else None
                            boxes = meta.get("boxes") if isinstance(meta, dict) else None
                            engine_id = meta.get("engine", engine_manager.current_id)
                            if window is not None:
                                window.set_ocr_boxes(boxes)
                                window.set_ocr_canvas_frames(raw_frame, preprocessed_frame, boxes)
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            logger.info("[%s] [%s] [Conf: %.2f] %s", timestamp, engine_id, conf, text)
                            if text:
                                if window is not None:
                                    window.set_ocr_result(text, float(conf), engine_id, timestamp)
                            if settings_state["auto_copy"] and text:
                                from PyQt6.QtWidgets import QApplication
                                QApplication.clipboard().setText(text)

                            if window is not None:
                                window.side_menu.update_openai_usage(openai_validator.cost_estimate_chars)

                            if window is not None:
                                summary_text = _build_status_summary(meta=meta, conf=float(conf or 0.0), elapsed_ms=elapsed_ms)
                                window.set_status("Done", summary_text)
                        else:
                            logger.info("[OCR] capture_once returned None (%.1f ms)",
                                        elapsed_ms)
                            if is_manual and window is not None:
                                # Manual mode: show "Ready" so user knows the action completed
                                window.set_status("Ready", "")
                            # Auto mode: silent — unchanged frames produce no status noise

                        # Simple cooldown — does NOT touch ocr_trigger, so stabilize /
                        # Re-capture triggers are preserved for the main consumer
                        # at the top of the loop.
                        await asyncio.sleep(0.5)

                    except Exception as exc:
                        logger.error("[OCR] Task crashed: %s", exc, exc_info=True)
                        await asyncio.sleep(1.0)

            preview_task = asyncio.create_task(_preview_task())
            ocr_task = asyncio.create_task(_ocr_task())
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

                res = await engine_manager.run_ocr(frame, line_count=_selected_line_count())
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
                    logger.info(
                        "[%s] [Engine: %s] [Conf: %.2f] "
                        "[Val: %s, changed=%s, ok=%s] %s",
                        timestamp, engine_id, conf,
                        "on" if v_enabled else "off", v_changed, v_valid, text,
                    )
                else:
                    print(".", end="", flush=True)

                await asyncio.sleep(1.5)
                continue

            res = await pipeline.capture_once(line_count=_selected_line_count())
            
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
                logger.info(
                    "[%s] [Engine: %s] [Conf: %.2f] "
                    "[Val: %s, changed=%s, ok=%s] %s",
                    timestamp, engine_id, conf,
                    "on" if v_enabled else "off", v_changed, v_valid, text,
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
        logger.info("Cleaning up resources...")
        cv2.destroyAllWindows()
        capture.stop()
        if google_vision is not None:
            try:
                await google_vision.close()
            except Exception:  # noqa: BLE001
                pass
        await engine_manager.dispose_all()
        await openai_validator.dispose()
        await deepseek_validator.dispose()
        logger.info("Stopped.")

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
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        try:
            from PyQt5.QtWidgets import QApplication, QMessageBox
        except ImportError:
            print("ERROR: Install PyQt6 or PyQt5")
            sys.exit(1)
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
        window.set_status("Ready", window_title or hex(hwnd))
        window.show()
        if hwnd is not None:
            window.controls_bar.set_streaming(True)
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
