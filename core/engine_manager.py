import asyncio
import logging
import os
import math
from collections import deque
import cv2
import numpy as np

from core.ocr_engine import PaddleOCR
from core.tensor_utils import (
    PAD_LEFT,
    PAD_RIGHT,
    PAD_TOP,
    PAD_BOTTOM,
    crop_box,
    preprocess_paddle_slice,
    preprocess_natural_slice,
)
from logic.validator import clean_ocr_output, clean_ocr_output_enhanced, is_valid_japanese, score_japanese_density

logger = logging.getLogger(__name__)

_VN_STABLE_MODE = os.getenv("DESKTOCR_VN_STABLE_MODE", "1") == "1"

_DET_MIN_WIDTH_PCT = float(os.getenv("DESKTOCR_MIN_W_PCT", "0.015"))
_DET_MIN_HEIGHT_PCT = float(os.getenv("DESKTOCR_MIN_H_PCT", "0.05"))
_DET_MIN_AREA_PCT = float(os.getenv("DESKTOCR_MIN_AREA_PCT", "0.00015"))
_DET_MIN_WIDTH_ABS = int(os.getenv("DESKTOCR_MIN_W_ABS", "8"))
_DET_MIN_HEIGHT_ABS = int(os.getenv("DESKTOCR_MIN_H_ABS", "8"))
_DET_MIN_AREA_ABS = int(os.getenv("DESKTOCR_MIN_AREA_ABS", "80"))
_DET_MAX_ASPECT = float(os.getenv("DESKTOCR_MAX_ASPECT", "45"))
_DET_MIN_ASPECT = float(os.getenv("DESKTOCR_MIN_ASPECT", "0.5"))
_REC_PAD_PX = int(os.getenv("DESKTOCR_REC_PAD_PX", "4"))
_REC_MIN_CONF = float(os.getenv("DESKTOCR_REC_MIN_CONF", "0.50"))
_MERGE_Y_TOL_PCT = float(os.getenv("DESKTOCR_MERGE_Y_TOL_PCT", "0.08"))

_PRUNE_MIN_AREA_RATIO = float(os.getenv("DESKTOCR_PRUNE_MIN_AREA_RATIO", "0.0005"))  # JP glyphs typically >0.003 in 800x50 crops
_PRUNE_MIN_SCORE = float(os.getenv("DESKTOCR_PRUNE_MIN_SCORE", "0.01"))
_PRUNE_DENSITY_LOG_THRESHOLD = float(os.getenv("DESKTOCR_PRUNE_DENSITY_LOG", "-0.6"))
_PRUNE_DENSITY_SUSPECT_THRESHOLD = float(os.getenv("DESKTOCR_PRUNE_DENSITY_SUSPECT", "-0.5"))
if _PRUNE_DENSITY_SUSPECT_THRESHOLD < _PRUNE_DENSITY_LOG_THRESHOLD:
    _PRUNE_DENSITY_SUSPECT_THRESHOLD = _PRUNE_DENSITY_LOG_THRESHOLD
_PRUNE_LARGE_AREA_RATIO = float(os.getenv("DESKTOCR_PRUNE_LARGE_AREA_RATIO", "0.20"))
_PRUNE_LARGE_AREA_DENSITY_LOG_THRESHOLD = float(os.getenv("DESKTOCR_PRUNE_LARGE_AREA_DENSITY_LOG", "-0.75"))
_PRUNE_MAX_BOXES = int(os.getenv("DESKTOCR_PRUNE_MAX_PER_SLICE", "36"))
_PRUNE_LOW_SCORE_STREAK = int(os.getenv("DESKTOCR_PRUNE_LOW_SCORE_STREAK", "7"))
_PRUNE_MIN_DENSITY_PIXELS = int(os.getenv("DESKTOCR_PRUNE_MIN_DENSITY_PIXELS", "120"))
_PRUNE_MIN_BOX_WIDTH = int(os.getenv("DESKTOCR_PRUNE_MIN_BOX_W", "18"))
_PRUNE_MIN_BOX_HEIGHT = int(os.getenv("DESKTOCR_PRUNE_MIN_BOX_H", "18"))
_PRUNE_DEDUP_IOU = float(os.getenv("DESKTOCR_PRUNE_DEDUP_IOU", "0.4"))
_PRUNE_DEDUP_SCORE_DELTA = float(os.getenv("DESKTOCR_PRUNE_DEDUP_SCORE_DELTA", "0.05"))
_PRUNE_DEDUP_CENTER_TOL = float(os.getenv("DESKTOCR_PRUNE_DEDUP_CENTER_TOL", "4"))
_PRUNE_DEDUP_WIDTH_TOL = float(os.getenv("DESKTOCR_PRUNE_DEDUP_WIDTH_TOL", "6"))
_PRUNE_DEDUP_HEIGHT_TOL = float(os.getenv("DESKTOCR_PRUNE_DEDUP_HEIGHT_TOL", "3"))
_PRUNE_DEDUP_MAX_RESULT = int(os.getenv("DESKTOCR_PRUNE_DEDUP_MAX_RESULT", "32"))
_PRUNE_DEDUP_COLLAPSE_Y_TOL = int(os.getenv("DESKTOCR_PRUNE_DEDUP_COLLAPSE_Y_TOL", "6"))
_PRUNE_DEDUP_MIN_RESULT = int(os.getenv("DESKTOCR_PRUNE_DEDUP_MIN_RESULT", "8"))
_PRUNE_DEDUP_CLAMP_GAP = float(os.getenv("DESKTOCR_PRUNE_DEDUP_CLAMP_GAP", "8"))
_PRUNE_DEDUP_SPLIT_TARGET_WIDTH = int(os.getenv("DESKTOCR_PRUNE_DEDUP_SPLIT_TARGET_WIDTH", "220"))
_PRUNE_DEDUP_SPLIT_MIN_WIDTH = int(os.getenv("DESKTOCR_PRUNE_DEDUP_SPLIT_MIN_WIDTH", "160"))
_PRUNE_DEDUP_SPLIT_PAD = int(os.getenv("DESKTOCR_PRUNE_DEDUP_SPLIT_PAD", "4"))
_PRUNE_SINGLE_SPAN_MODE = os.getenv("DESKTOCR_SINGLE_SPAN_MODE", "1") == "1"
_PRUNE_DEDUP_SPLIT_FLAG = "__split_segment__"
_PRUNE_SINGLE_SPAN_FLAG = "__single_span__"
_PRUNE_MAX_FILTERED_BOXES = int(os.getenv("DESKTOCR_MAX_FILTERED_BOXES", "16"))
_FILTER_DUP_X_TOL = int(os.getenv("DESKTOCR_FILTER_DUP_X_TOL", "2"))
_FILTER_DUP_H_TOL = int(os.getenv("DESKTOCR_FILTER_DUP_H_TOL", "2"))
_FILTER_RECENT_CACHE = max(1, int(os.getenv("DESKTOCR_FILTER_RECENT_CACHE", "32")))
_VN_SPAN_TIER_A_MIN = float(os.getenv("DESKTOCR_VN_SPAN_TIER_A_MIN", "0.20"))
_VN_SPAN_TIER_B_MIN = float(os.getenv("DESKTOCR_VN_SPAN_TIER_B_MIN", "0.50"))
_VN_SPAN_TIER_A_TARGET = float(os.getenv("DESKTOCR_VN_SPAN_TIER_A_TARGET", "0.49"))

_TRIM_PAD_ENABLED = os.getenv("DESKTOCR_TRIM_PAD_ENABLE", "1") == "1"
_TRIM_PAD_BOOST_ENABLED = os.getenv("DESKTOCR_TRIM_PAD_BOOST_ENABLE", "1") == "1"
_TRIM_PAD_MARGIN = int(os.getenv("DESKTOCR_TRIM_PAD_MARGIN_PX", "3"))
_TRIM_PAD_PROJ_THRESH = float(os.getenv("DESKTOCR_TRIM_PAD_PROJ_THRESH", "0.05"))

VN_STABLE_CONFIG = {
    "det_score_thresh": 0.50,
    "max_filtered_boxes": 16,
    "dup_x_tol": 2,
    "dup_h_tol": 2,
    "dup_cache": 32,
    "tier_a_min": 0.20,
    "tier_b_min": 0.50,
    "tier_a_target": 0.49,
    "single_span": True,
    "trim_pad_boost": False,
    "expand_for_recognition": True,
}

if _VN_STABLE_MODE:
    _PRUNE_SINGLE_SPAN_MODE = VN_STABLE_CONFIG["single_span"]
    _PRUNE_MAX_FILTERED_BOXES = VN_STABLE_CONFIG["max_filtered_boxes"]
    _FILTER_DUP_X_TOL = VN_STABLE_CONFIG["dup_x_tol"]
    _FILTER_DUP_H_TOL = VN_STABLE_CONFIG["dup_h_tol"]
    _FILTER_RECENT_CACHE = VN_STABLE_CONFIG["dup_cache"]
    _VN_SPAN_TIER_A_MIN = VN_STABLE_CONFIG["tier_a_min"]
    _VN_SPAN_TIER_B_MIN = VN_STABLE_CONFIG["tier_b_min"]
    _VN_SPAN_TIER_A_TARGET = VN_STABLE_CONFIG["tier_a_target"]
    _TRIM_PAD_BOOST_ENABLED = VN_STABLE_CONFIG["trim_pad_boost"]
    logger.info(
        "[VNStable] Stable mode active; locking VN parameters (det=%.2f, cap=%d, span_tiers=%s)",
        VN_STABLE_CONFIG["det_score_thresh"],
        VN_STABLE_CONFIG["max_filtered_boxes"],
        {
            "tier_a_min": VN_STABLE_CONFIG["tier_a_min"],
            "tier_b_min": VN_STABLE_CONFIG["tier_b_min"],
            "tier_a_target": VN_STABLE_CONFIG["tier_a_target"],
        },
    )

MIN_PRIMARY_JP_CHARS = 3
MIN_CANDIDATE_JP_RATIO = 0.30
MIN_CANDIDATE_JP_CHARS = 3
MAX_FALLBACK_BANDS = 2
MIN_FALLBACK_GAIN_JP_CHARS = 2
MIN_FALLBACK_GAIN_TEXT_CHARS = 3

_CROP_SAVE_COUNTER = 0


def _web_parity_mode_enabled() -> bool:
    return os.getenv("DESKTOCR_WEB_PARITY_MODE", "0") == "1"


def _raw_ocr_mode_enabled() -> bool:
    return os.getenv("DESKTOCR_RAW_OCR_MODE", "0") == "1"


def _validator_disabled() -> bool:
    return os.getenv("DESKTOCR_DISABLE_VALIDATOR", "0") == "1"


class UnavailableEngine:
    def __init__(self, engine_id: str, reason: str):
        self.engine_id = engine_id
        self.reason = reason

    async def recognize(self, _image: np.ndarray) -> dict:
        return {
            "text": "",
            "confidence": 0.0,
            "meta": {
                "warning": self.reason,
                "engine": self.engine_id,
            },
        }

    async def dispose(self):
        return


class EasyOCREngine:
    def __init__(self):
        self._reader = None
        self._load_lock = asyncio.Lock()

    async def load(self):
        async with self._load_lock:
            if self._reader is not None:
                return self

            def _build_reader():
                import easyocr

                return easyocr.Reader(["ja", "en"], gpu=False, verbose=False)

            loop = asyncio.get_running_loop()
            self._reader = await loop.run_in_executor(None, _build_reader)
        return self

    async def recognize(self, image: np.ndarray) -> dict:
        if self._reader is None:
            return {
                "text": "",
                "confidence": 0.0,
                "meta": {"warning": "easyocr_not_loaded", "engine": "easyocr"},
            }

        loop = asyncio.get_running_loop()

        def _run_readtext():
            return self._reader.readtext(image, detail=1, paragraph=False)

        rows = await loop.run_in_executor(None, _run_readtext)
        texts: list[str] = []
        confidences: list[float] = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 3:
                continue
            text = str(row[1] or "").strip()
            conf = float(row[2] or 0.0)
            if text:
                texts.append(text)
                confidences.append(conf)

        final_text = "\n".join(texts)
        avg_conf = float(sum(confidences) / len(confidences)) if confidences else 0.0
        return {
            "text": final_text,
            "confidence": avg_conf,
            "meta": {
                "boxes_raw": len(rows),
                "boxes_merged": 0,
                "fallback_used": False,
                "ocr_chars": len(final_text),
                "engine": "easyocr",
            },
        }

    async def dispose(self):
        self._reader = None

class EngineManager:
    def _dbg(self, msg, *args, **kwargs):
        logger.debug(msg, *args, **kwargs)

    def __init__(self, models_dir: str, model_config: dict):
        self.models_dir = models_dir
        self.model_config = model_config
        self._telemetry = {
            "frames": 0,
            "boxes_raw": 0,
            "boxes_merged": 0,
            "fallback_hits": 0,
            "ocr_chars": 0,
            "boxes_pruned": 0,
            "suspect_density": 0,
            "dedup_dropped": 0,
            "cap_hits": 0,
            "normalized_boxes": 0,
            "trimmed_boxes": 0,
            "padded_boxes": 0,
            "boost_candidates": 0,
        }
        
        self._engine_aliases = {
            "server": "paddle",
        }
        self._engines = {
            "paddle": {"instance": None, "state": "not_loaded", "task": None},
            "windows_ocr": {"instance": None, "state": "not_loaded", "task": None},
            "easyocr": {"instance": None, "state": "not_loaded", "task": None},
        }
        
        self._current_id = None
        self._current_instance = None
        self._switch_lock = asyncio.Lock()

    def _resolve_engine_id(self, engine_id: str) -> str:
        return self._engine_aliases.get(engine_id, engine_id)

    def get_supported_engines(self) -> list[str]:
        return list(self._engines.keys())

    def get_engine_status(self) -> dict[str, dict]:
        statuses: dict[str, dict] = {}
        for engine_id, meta in self._engines.items():
            statuses[engine_id] = {
                "state": meta.get("state", "unknown"),
                "loaded": bool(meta.get("instance") is not None),
                "ready": bool(meta.get("state") == "ready"),
            }

        statuses["paddle"]["note"] = "primary_accuracy_pipeline"
        statuses["windows_ocr"]["note"] = "guarded_runtime_engine"

        try:
            __import__("easyocr")
            statuses["easyocr"]["dependency"] = "installed"
        except Exception:
            statuses["easyocr"]["dependency"] = "missing"
            statuses["easyocr"]["note"] = "install easyocr to enable"

        return statuses

    async def switch_engine(self, engine_id: str) -> bool:
        resolved_engine_id = self._resolve_engine_id(engine_id)

        if resolved_engine_id not in self._engines:
            logger.error(f"Engine '{engine_id}' is not supported.")
            return False
            
        async with self._switch_lock:
            if self._current_id == resolved_engine_id and self._engines[resolved_engine_id]["state"] == "ready":
                return True
                
            try:
                instance = await self.get_or_load_engine(resolved_engine_id)
                self._current_id = resolved_engine_id
                self._current_instance = instance
                logger.info(f"Successfully switched to engine: {resolved_engine_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to switch to engine {resolved_engine_id}: {e}")
                return False

    async def get_or_load_engine(self, engine_id: str):
        resolved_engine_id = self._resolve_engine_id(engine_id)
        meta = self._engines.get(resolved_engine_id)
        if not meta:
            raise ValueError(f"Unknown engine: {resolved_engine_id}")
            
        if meta["state"] == "ready":
            return meta["instance"]
            
        if meta["state"] == "loading":
            if meta["task"] is not None:
                return await asyncio.shield(meta["task"])
            # task is None but still loading — wait briefly and retry
            await asyncio.sleep(0.05)
            return await self.get_or_load_engine(engine_id)
            
        # State is not_loaded or error: start a new load concurrently
        meta["state"] = "loading"
        
        async def _load_task():
            try:
                if resolved_engine_id == "paddle":
                    engine = PaddleOCR(self.models_dir, self.model_config)
                    await engine.load()
                elif resolved_engine_id == "windows_ocr":
                    engine = await self._load_windows_ocr()
                elif resolved_engine_id == "easyocr":
                    engine = await self._load_easyocr()
                else:
                    raise ValueError(f"Unknown engine ID '{resolved_engine_id}'")
                    
                meta["instance"] = engine
                meta["state"] = "ready"
                return engine
            except Exception as e:
                meta["state"] = "error"
                raise e
            finally:
                meta["task"] = None
                
        # Assignment must be synchronous to deduplicate concurrent requests waiting for event loop
        task = asyncio.create_task(_load_task())
        meta["task"] = task
        
        return await task

    async def run_ocr(self, image: np.ndarray, line_count: int = 1) -> dict:
        if not self._current_instance:
            logger.error("No active engine to run OCR.")
            return self._normalize_result("", 0.0, {"warning": "no_active_engine"})
            
        final_text = ""
        final_conf = 0.0
        base_meta: dict[str, object] = {}
        work_image: np.ndarray | None = image

        try:
            if self._current_id == "paddle":
                line_count = max(1, int(line_count or 1))
                bands = self._slice_into_bands(image, line_count)
                if not bands:
                    return self._normalize_result("", 0.0, {"warning": "empty_frame"})
                logger.debug(
                    "[Slice] line_count=%d bands=%d frame=%dx%d",
                    line_count,
                    len(bands),
                    image.shape[1] if image is not None else -1,
                    image.shape[0] if image is not None else -1,
                )

                band_texts: list[str] = []
                band_confidences: list[float] = []
                aggregated_boxes: list[list[int]] = []
                boxes_raw_total = 0
                boxes_merged_total = 0
                fallback_used = False
                ocr_chars_total = 0
                processed_frames: list[np.ndarray] = []
                boxes_pruned_total = 0
                suspect_density_total = 0
                dedup_dropped_total = 0
                dedup_clusters_total = 0
                cap_hits_total = 0
                normalized_total = 0
                trimmed_total = 0
                padded_total = 0
                boost_total = 0
                suspect_details_sample: list[dict] | None = None

                for band_image, y1, _y2 in bands:
                    band_text, band_conf, band_meta, band_processed = await self._run_paddle_pass(band_image, y1)
                    band_texts.append(band_text)
                    band_confidences.append(band_conf)
                    aggregated_boxes.extend(band_meta.get("boxes", []))
                    boxes_raw_total += int(band_meta.get("boxes_raw", 0) or 0)
                    boxes_merged_total += int(band_meta.get("boxes_merged", 0) or 0)
                    fallback_used = fallback_used or bool(band_meta.get("fallback_used", False))
                    ocr_chars_total += int(band_meta.get("ocr_chars", len(band_text)))
                    boxes_pruned_total += int(band_meta.get("boxes_pruned", 0) or 0)
                    suspect_density_total += int(band_meta.get("suspect_density", 0) or 0)
                    dedup_dropped_total += int(band_meta.get("dedup_dropped", 0) or 0)
                    dedup_clusters_total += int(band_meta.get("dedup_clusters", 0) or 0)
                    cap_hits_total += int(band_meta.get("cap_hits", 0) or 0)
                    normalized_total += int(band_meta.get("normalized_boxes", 0) or 0)
                    trimmed_total += int(band_meta.get("trimmed_boxes", 0) or 0)
                    padded_total += int(band_meta.get("padded_boxes", 0) or 0)
                    boost_total += int(band_meta.get("boost_candidates", 0) or 0)
                    details = band_meta.get("suspect_density_details")
                    if not suspect_details_sample and isinstance(details, list) and details:
                        suspect_details_sample = details
                    if isinstance(band_processed, np.ndarray) and band_processed.size > 0:
                        processed_frames.append(band_processed)

                final_text = "\n".join(band_texts).strip()
                final_conf = float(sum(band_confidences) / len(band_confidences)) if band_confidences else 0.0
                base_meta = {
                    "boxes_raw": boxes_raw_total,
                    "boxes_merged": boxes_merged_total,
                    "fallback_used": fallback_used,
                    "ocr_chars": ocr_chars_total,
                    "boxes": aggregated_boxes,
                    "paddle_line_count": line_count,
                    "boxes_pruned": boxes_pruned_total,
                    "suspect_density": suspect_density_total,
                    "suspect_density_details": suspect_details_sample or [],
                    "dedup_dropped": dedup_dropped_total,
                    "dedup_clusters": dedup_clusters_total,
                    "cap_hits": cap_hits_total,
                    "normalized_boxes": normalized_total,
                    "trimmed_boxes": trimmed_total,
                    "padded_boxes": padded_total,
                    "boost_candidates": boost_total,
                }

                if len(processed_frames) == 1:
                    work_image = processed_frames[0]
                elif len(processed_frames) == len(bands) and processed_frames:
                    try:
                        work_image = np.vstack(processed_frames)
                    except ValueError:
                        work_image = preprocess_paddle_slice(image)
                else:
                    work_image = preprocess_paddle_slice(image)
            else:
                work_image = preprocess_natural_slice(image)
                rec = await self._current_instance.recognize(work_image)
                final_text = (rec.get("text", "") or "").strip()
                final_conf = float(rec.get("confidence", 0.0) or 0.0)
                base_meta = rec.get("meta", {}) if isinstance(rec, dict) else {}

            final_text, validator_meta = self._apply_validator_assist(final_text, final_conf)
            self._dbg(f"[Validator] {final_text}")
            combined_meta = dict(base_meta) if isinstance(base_meta, dict) else {}
            combined_meta.update(validator_meta)
            self._telemetry["frames"] += 1
            self._telemetry["boxes_raw"] += int(combined_meta.get("boxes_raw", 0) or 0)
            self._telemetry["boxes_merged"] += int(combined_meta.get("boxes_merged", 0) or 0)
            self._telemetry["fallback_hits"] += int(bool(combined_meta.get("fallback_used", False)))
            self._telemetry["ocr_chars"] += len(final_text)
            self._telemetry["boxes_pruned"] += int(combined_meta.get("boxes_pruned", 0) or 0)
            self._telemetry["suspect_density"] += int(combined_meta.get("suspect_density", 0) or 0)
            self._telemetry["dedup_dropped"] += int(combined_meta.get("dedup_dropped", 0) or 0)
            self._telemetry["cap_hits"] += int(combined_meta.get("cap_hits", 0) or 0)
            self._telemetry["normalized_boxes"] += int(combined_meta.get("normalized_boxes", 0) or 0)
            self._telemetry["trimmed_boxes"] += int(combined_meta.get("trimmed_boxes", 0) or 0)
            self._telemetry["padded_boxes"] += int(combined_meta.get("padded_boxes", 0) or 0)
            self._telemetry["boost_candidates"] += int(combined_meta.get("boost_candidates", 0) or 0)

            result = self._normalize_result(final_text, final_conf, combined_meta)
            if isinstance(work_image, np.ndarray) and work_image.size > 0:
                result["preprocessed_frame"] = work_image.copy()
            return result
        except Exception as e:
            logger.error(f"Error running OCR pipeline: {e}")
            return self._normalize_result("", 0.0, {"warning": str(e)})

    async def _run_paddle_pass(self, image: np.ndarray, y_offset: int) -> tuple[str, float, dict, np.ndarray]:
        work_image = preprocess_paddle_slice(image)
        detected_boxes = await self._current_instance.detect(work_image)
        boxes_raw = len(detected_boxes)
        h_img, w_img = work_image.shape[:2]
        filtered_boxes = self._filter_boxes(detected_boxes, w_img, h_img)
        deduped_boxes, dedup_stats = self._deduplicate_boxes(filtered_boxes)
        pruned_boxes, prune_stats = self._apply_pre_recognition_gate(work_image, deduped_boxes)

        recognition_boxes = pruned_boxes
        span_meta: dict[str, object] | None = None
        if _PRUNE_SINGLE_SPAN_MODE and pruned_boxes:
            recognition_boxes, span_meta = self._collapse_to_single_span(pruned_boxes, w_img, h_img)

        expand_for_recognition = (
            VN_STABLE_CONFIG["expand_for_recognition"]
            if _VN_STABLE_MODE
            else (os.getenv("DESKTOCR_PADDLE_EXPAND", "1") == "1")
        )

        primary, rec_stats = await self._recognize_box_groups(
            work_image,
            recognition_boxes,
            expand_for_recognition=expand_for_recognition,
        )
        final_text = (primary.get("text", "") or "").strip()
        final_conf = float(primary.get("confidence", 0.0) or 0.0)
        offset_boxes: list[list[int]] = []
        for box in recognition_boxes:
            if len(box) < 4:
                continue
            x1, y1, x2, y2 = box[:4]
            offset_boxes.append([x1, y1 + y_offset, x2, y2 + y_offset])

        meta = {
            "boxes_raw": boxes_raw,
            "boxes_merged": 0,
            "fallback_used": False,
            "ocr_chars": len(final_text),
            "boxes": offset_boxes,
            "boxes_pruned": prune_stats.get("dropped", 0),
            "boxes_after_prune": prune_stats.get("kept", len(offset_boxes)),
            "prune_reasons": prune_stats.get("reasons", {}),
            "suspect_density": prune_stats.get("suspect_density", 0),
            "suspect_density_details": prune_stats.get("suspect_details", []),
            "dedup_dropped": dedup_stats.get("dropped", 0),
            "dedup_clusters": dedup_stats.get("clusters", 0),
            "cap_hits": prune_stats.get("cap_hits", 0),
            "normalized_boxes": rec_stats.get("normalized", 0),
            "trimmed_boxes": rec_stats.get("trimmed", 0),
            "padded_boxes": rec_stats.get("padded", 0),
            "boost_candidates": rec_stats.get("boosted", 0),
        }
        if span_meta:
            meta.update(span_meta)
        return final_text, final_conf, meta, work_image

    def _apply_validator_assist(self, text: str, confidence: float) -> tuple[str, dict]:
        if not text:
            return "", {"validator": {"enabled": not _validator_disabled(), "changed": False, "valid_hint": False, "jp_chars": 0}}

        if _validator_disabled():
            return text, {"validator": {"enabled": False, "changed": False, "valid_hint": True, "jp_chars": int(score_japanese_density(text))}}

        cleaned = clean_ocr_output_enhanced(text)
        out_text = cleaned if cleaned else text
        changed = out_text != text
        jp_chars = int(score_japanese_density(out_text))
        valid_hint = bool(is_valid_japanese(out_text, confidence)) if out_text else False

        return out_text, {
            "validator": {
                "enabled": True,
                "changed": changed,
                "valid_hint": valid_hint,
                "jp_chars": jp_chars,
            }
        }

    def _normalize_result(self, text: str, confidence: float, meta: dict | None = None) -> dict:
        normalized_meta = {
            "engine": self._current_id,
            "boxes_raw": 0,
            "boxes_merged": 0,
            "fallback_used": False,
            "ocr_chars": len(text or ""),
            "boxes": [],
        }
        if isinstance(meta, dict):
            normalized_meta.update(meta)
        return {
            "text": (text or "").strip(),
            "confidence": float(confidence or 0.0),
            "meta": normalized_meta,
        }

    def _slice_into_bands(self, image: np.ndarray, line_count: int) -> list[tuple[np.ndarray, int, int]]:
        if image is None or image.size == 0:
            return []
        line_count = max(1, int(line_count or 1))
        h_total = image.shape[0]
        if h_total <= 0:
            return []
        edges = [int(round(i * h_total / line_count)) for i in range(line_count + 1)]
        bands: list[tuple[np.ndarray, int, int]] = []
        for idx in range(line_count):
            y1 = edges[idx]
            y2 = edges[idx + 1]
            if (y2 - y1) <= 0:
                continue
            band = image[y1:y2, :, :]
            if band.size == 0:
                continue
            bands.append((band, y1, y2))
        return bands

    def _normalize_box(self, box: list, w: int, h: int) -> tuple[int, int, int, int] | None:
        x1 = int(math.floor(float(box[0])))
        y1 = int(math.floor(float(box[1])))
        x2 = int(math.ceil(float(box[2])))
        y2 = int(math.ceil(float(box[3])))
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if (x2 - x1) < 4 or (y2 - y1) < 4:
            return None
        return x1, y1, x2, y2

    def _expand_box_for_recognition(self, box: tuple[int, int, int, int], w: int, h: int) -> tuple[int, int, int, int] | None:
        x1, y1, x2, y2 = box
        bw = x2 - x1
        bh = y2 - y1
        if bw < 4 or bh < 4:
            return None

        # VN-optimized tight crop: anisotropic padding to avoid clipping kana.
        pad_x = 2
        pad_y = 8
        ex1 = max(0, x1 - pad_x)
        ey1 = max(0, y1 - pad_y)
        ex2 = min(w, x2 + pad_x)
        ey2 = min(h, y2 + pad_y)

        if (ex2 - ex1) < 4 or (ey2 - ey1) < 4:
            return None
        return ex1, ey1, ex2, ey2

    def _filter_boxes(self, boxes: list, w: int, h: int) -> list[list[int]]:
        total = len(boxes)
        if not boxes:
            logger.info("[BoxFilter] 0/0 boxes kept after filtering (image %dx%d)", w, h)
            return []

        min_w = max(_DET_MIN_WIDTH_ABS, int(w * _DET_MIN_WIDTH_PCT))
        min_h = max(_DET_MIN_HEIGHT_ABS, int(h * _DET_MIN_HEIGHT_PCT))
        min_area = max(_DET_MIN_AREA_ABS, int(w * h * _DET_MIN_AREA_PCT))

        kept: list[list[int]] = []
        kept_scores: list[tuple[float, int]] = []
        recent = deque(maxlen=_FILTER_RECENT_CACHE)
        dedup_hits = 0
        dedup_log_budget = 5
        for b in boxes:
            norm = self._normalize_box(b[:4], w, h)
            if norm is None:
                continue
            x1, y1, x2, y2 = norm
            bw = x2 - x1
            bh = y2 - y1
            area = bw * bh
            aspect = (bw / bh) if bh > 0 else 0.0

            reject_reason = None
            if bw < min_w:
                reject_reason = "width_too_small"
            elif bh < min_h:
                reject_reason = "height_too_small"
            elif area < min_area:
                reject_reason = "area_too_small"
            elif aspect < _DET_MIN_ASPECT or aspect > _DET_MAX_ASPECT:
                reject_reason = "aspect_ratio"

            if reject_reason:
                logger.debug(
                    "[BoxFilter] REJECTED box [%.0f,%.0f,%.0f,%.0f] w=%.0f h=%.0f area=%.0f aspect=%.2f | reason=%s",
                    x1, y1, x2, y2, bw, bh, area, aspect, reject_reason,
                )
                continue

            dup_hit = False
            for rx1, ry1, rx2, ry2 in recent:
                if (
                    abs(rx1 - x1) <= _FILTER_DUP_X_TOL
                    and abs(rx2 - x2) <= _FILTER_DUP_X_TOL
                    and abs((ry2 - ry1) - (y2 - y1)) <= _FILTER_DUP_H_TOL
                ):
                    dup_hit = True
                    break

            if dup_hit:
                dedup_hits += 1
                if dedup_hits <= dedup_log_budget:
                    self._dbg(
                        "[FilterDedup] suppressed near-duplicate box [%.0f,%.0f,%.0f,%.0f] (hits=%d)",
                        x1,
                        y1,
                        x2,
                        y2,
                        dedup_hits,
                    )
                continue

            kept_box = [x1, y1, x2, y2]
            if len(b) > 4:
                kept_box.extend(b[4:])
            kept.append(kept_box)
            score = float(b[4]) if len(b) > 4 else 0.0
            kept_scores.append((score, len(kept_scores)))
            recent.append((x1, y1, x2, y2))
            logger.debug(
                "[BoxFilter] KEPT box [%.0f,%.0f,%.0f,%.0f] w=%.0f h=%.0f area=%.0f aspect=%.2f",
                x1, y1, x2, y2, bw, bh, area, aspect,
            )

        if _PRUNE_MAX_FILTERED_BOXES > 0 and len(kept) > _PRUNE_MAX_FILTERED_BOXES:
            sorted_idx = sorted(
                range(len(kept_scores)),
                key=lambda idx: kept_scores[idx][0],
                reverse=True,
            )
            selected_idx = sorted(sorted_idx[:_PRUNE_MAX_FILTERED_BOXES])
            dropped = len(kept) - len(selected_idx)
            kept = [kept[idx] for idx in selected_idx]
            self._dbg(
                "[FilterCap] trimmed %d boxes (limit=%d, selected_scores=%s)",
                dropped,
                _PRUNE_MAX_FILTERED_BOXES,
                [f"{kept_scores[idx][0]:.3f}" for idx in selected_idx[:4]],
            )

        logger.info(
            "[BoxFilter] %d/%d boxes kept after filtering (image %dx%d, dup_hits=%d)",
            len(kept),
            total,
            w,
            h,
            dedup_hits,
        )

        self._dbg(f"[Filter] Kept boxes: {kept}")

        return kept

    def _apply_pre_recognition_gate(self, image: np.ndarray, boxes: list[list[int]]) -> tuple[list[list[int]], dict]:
        if not boxes:
            return [], {"kept": 0, "dropped": 0, "reasons": {}, "suspect_density": 0, "suspect_details": [], "cap_hits": 0}

        h, w = image.shape[:2]
        frame_area = max(1, w * h)
        kept: list[list[int]] = []
        stats = {"kept": 0, "dropped": 0, "reasons": {}, "suspect_density": 0, "suspect_details": [], "cap_hits": 0}
        low_score_run = 0
        cap_logged = False

        for idx, box in enumerate(boxes):
            x1, y1, x2, y2 = box[:4]
            bw = max(1, int(round(x2 - x1)))
            bh = max(1, int(round(y2 - y1)))
            area = bw * bh
            area_ratio = float(area) / float(frame_area)
            score = float(box[4]) if len(box) > 4 else None

            reason = None
            density_log = None

            if bw < _PRUNE_MIN_BOX_WIDTH or bh < _PRUNE_MIN_BOX_HEIGHT:
                reason = "min_size"
            elif area_ratio < _PRUNE_MIN_AREA_RATIO:
                reason = "area"
            elif score is not None and score < _PRUNE_MIN_SCORE:
                reason = "score"
                low_score_run += 1
            else:
                low_score_run = 0

            if reason is None:
                is_split_segment = self._is_split_segment(box)
                if is_split_segment:
                    density_log = None
                else:
                    density_log = self._estimate_box_density(image, (x1, y1, x2, y2), area)
                density_drop_threshold = _PRUNE_DENSITY_LOG_THRESHOLD
                suspect_threshold = _PRUNE_DENSITY_SUSPECT_THRESHOLD
                if _PRUNE_LARGE_AREA_RATIO > 0.0 and area_ratio >= _PRUNE_LARGE_AREA_RATIO:
                    density_drop_threshold = _PRUNE_LARGE_AREA_DENSITY_LOG_THRESHOLD
                    suspect_threshold = max(suspect_threshold, density_drop_threshold)

                if density_log is not None and density_log < density_drop_threshold:
                    reason = "density"
                elif density_log is not None and density_log < suspect_threshold:
                    stats["suspect_density"] += 1
                    if len(stats["suspect_details"]) < 16:
                        stats["suspect_details"].append(
                            {
                                "idx": idx,
                                "density": density_log,
                                "area_ratio": area_ratio,
                                "score": score,
                            }
                        )
                    self._dbg(
                        f"[PruneSuspect] box#{idx} density={density_log:.6f} area_ratio={area_ratio:.6f} "
                        f"score={score if score is not None else 'n/a'}"
                    )

            if reason is None and _PRUNE_MAX_BOXES > 0 and len(kept) >= _PRUNE_MAX_BOXES:
                reason = "cap"
                stats["cap_hits"] += 1
                if not cap_logged:
                    self._dbg(f"[PruneCap] Hit {_PRUNE_MAX_BOXES} boxes, applying hard cap")
                    cap_logged = True

            if reason:
                stats["dropped"] += 1
                stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1
                self._dbg(
                    f"[Prune] box#{idx} reason={reason} score={score if score is not None else 'n/a'} "
                    f"area_ratio={area_ratio:.6f} density={density_log if density_log is not None else 'n/a'}"
                )
                if (
                    score is not None
                    and score < _PRUNE_MIN_SCORE
                    and _PRUNE_LOW_SCORE_STREAK > 0
                    and low_score_run >= _PRUNE_LOW_SCORE_STREAK
                ):
                    remaining = len(boxes) - idx - 1
                    if remaining > 0:
                        stats["dropped"] += remaining
                        stats["reasons"]["low_score_run"] = stats["reasons"].get("low_score_run", 0) + remaining
                        self._dbg(f"[Prune] low_score_run hit, skipping remaining {remaining} boxes")
                    break
                continue

            kept.append(box)

        stats["kept"] = len(kept)
        return kept, stats

    @classmethod
    def _get_box_meta(cls, box: list[int]) -> dict | None:
        if len(box) > 4 and isinstance(box[-1], dict):
            return box[-1]
        return None

    @classmethod
    def _set_box_flag(cls, box: list[int], flag: str) -> None:
        if not box:
            return
        meta = cls._get_box_meta(box)
        if meta is None:
            meta = {}
            box.append(meta)
        meta[flag] = True

    @classmethod
    def _has_box_flag(cls, box: list[int], flag: str) -> bool:
        meta = cls._get_box_meta(box)
        return bool(meta and meta.get(flag))

    @classmethod
    def _is_split_segment(cls, box: list[int]) -> bool:
        return cls._has_box_flag(box, _PRUNE_DEDUP_SPLIT_FLAG)

    @classmethod
    def _is_single_span(cls, box: list[int]) -> bool:
        return cls._has_box_flag(box, _PRUNE_SINGLE_SPAN_FLAG)

    def _should_skip_normalize(self, box: list[int]) -> bool:
        return self._is_split_segment(box) or self._is_single_span(box)

    def _deduplicate_boxes(self, boxes: list[list[int]]) -> tuple[list[list[int]], dict]:
        if not boxes:
            return [], {"dropped": 0, "clusters": 0}

        clusters: list[dict] = []

        for idx, box in enumerate(boxes):
            score = float(box[4]) if len(box) > 4 else 0.0
            match = None
            for cluster in clusters:
                score_delta = abs(score - cluster["score"])
                if score_delta > _PRUNE_DEDUP_SCORE_DELTA:
                    continue

                iou = self._box_iou(box, cluster["box"])
                if iou >= _PRUNE_DEDUP_IOU or self._boxes_horizontally_close(box, cluster["box"]):
                    match = cluster
                    break

            if match is None:
                clusters.append({
                    "box": box,
                    "score": score,
                    "first_seen": idx,
                    "members": [],
                    "size": 1,
                })
                continue

            match["size"] += 1
            if score > match["score"]:
                match["members"].append(match["box"])
                match["box"] = box
                match["score"] = score
            else:
                match["members"].append(box)

        clusters.sort(key=lambda c: c["first_seen"])
        deduped = [cluster["box"] for cluster in clusters]
        cluster_count = sum(1 for cluster in clusters if cluster["size"] > 1)

        deduped, clamp_meta = self._clamp_dedup_results(deduped)
        dropped = len(boxes) - len(deduped)

        collapse_meta = clamp_meta.get("collapse_meta")
        if collapse_meta:
            msg = (
                f"[DedupCollapse] boxes={collapse_meta['before']} -> {collapse_meta['after']}"
            )
            if "y_tol" in collapse_meta:
                msg += f" y_tol={collapse_meta['y_tol']}"
            if "gap" in collapse_meta:
                msg += f" gap={collapse_meta['gap']:.1f}"
            self._dbg(msg)
        split_meta = clamp_meta.get("split_meta")
        if split_meta:
            msg = f"[DedupSplit] boxes={split_meta['before']} -> {split_meta['after']}"
            if "target_w" in split_meta:
                msg += f" target_w={split_meta['target_w']}"
            self._dbg(msg)

        for cluster in clusters:
            if cluster["size"] <= 1:
                continue
            self._dbg(
                f"[Dedup] seed_idx={cluster['first_seen']} size={cluster['size']} "
                f"score={cluster['score']:.3f}"
            )

        stats = {"dropped": dropped, "clusters": cluster_count}
        if clamp_meta.get("collapse_meta"):
            stats["collapsed"] = True
        if clamp_meta.get("split_meta"):
            stats["split"] = True
        return deduped, stats

    def _clamp_dedup_results(self, boxes: list[list[int]]) -> tuple[list[list[int]], dict]:
        stats: dict[str, object] = {}
        if not boxes:
            return boxes, stats

        min_target = max(1, _PRUNE_DEDUP_MIN_RESULT)
        max_target = _PRUNE_DEDUP_MAX_RESULT if _PRUNE_DEDUP_MAX_RESULT > 0 else None

        if max_target is not None and len(boxes) > max_target:
            boxes, reduce_meta = self._reduce_box_count(boxes, max_target)
            if reduce_meta:
                stats["collapse_meta"] = reduce_meta
                stats["collapsed"] = True

        if not _PRUNE_SINGLE_SPAN_MODE and len(boxes) < min_target:
            boxes, split_meta = self._split_wide_boxes(boxes, min_target, max_target)
            if split_meta:
                stats["split_meta"] = split_meta
                stats["split"] = True

        if max_target is not None and len(boxes) > max_target:
            boxes = boxes[:max_target]

        return boxes, stats

    def _split_wide_boxes(
        self,
        boxes: list[list[int]],
        min_target: int,
        max_target: int | None,
    ) -> tuple[list[list[int]], dict | None]:
        if not boxes:
            return boxes, None

        expanded: list[list[int]] = [list(b) for b in boxes]
        stats: dict[str, object] | None = None
        target_w = max(1, _PRUNE_DEDUP_SPLIT_TARGET_WIDTH)
        min_w = max(1, _PRUNE_DEDUP_SPLIT_MIN_WIDTH)
        forced_min_w = max(1, min_w // 2)
        pad = max(0, _PRUNE_DEDUP_SPLIT_PAD)
        band_left = min(b[0] for b in expanded)
        band_right = max(b[2] for b in expanded)
        performed_split = False

        while len(expanded) < min_target:
            idx = max(range(len(expanded)), key=lambda i: max(1, expanded[i][2] - expanded[i][0]))
            box = expanded[idx]
            width = max(1, box[2] - box[0])
            rest = box[4:]

            if width < forced_min_w:
                break

            expanded.pop(idx)
            segments = max(2, int(math.ceil(width / target_w))) if width >= min_w else 2
            needed = max(0, min_target - len(expanded))
            if needed > 0:
                segments = max(segments, needed)
            new_boxes: list[list[int]] = []
            cursor = box[0]
            for seg in range(segments):
                remaining = segments - seg
                max_remaining = box[2] - cursor
                slice_w = max(
                    forced_min_w,
                    min(target_w, max_remaining - forced_min_w * (remaining - 1)),
                )
                end = cursor + slice_w
                if end > box[2] or remaining == 1:
                    end = box[2]
                padded_start = cursor
                padded_end = end
                if pad > 0:
                    padded_start = max(band_left, cursor - pad)
                    padded_end = min(band_right, end + pad)
                new_box = [padded_start, box[1], padded_end, box[3], *rest]
                self._set_box_flag(new_box, _PRUNE_DEDUP_SPLIT_FLAG)
                new_boxes.append(new_box)
                cursor = end
                if cursor >= box[2]:
                    break
            expanded[idx:idx] = new_boxes
            stats = stats or {
                "split": True,
                "before": len(boxes),
                "target_w": target_w,
            }
            performed_split = True

            break

        if performed_split:
            expanded = self._dedupe_split_segments(expanded)

        if max_target is not None and len(expanded) > max_target:
            expanded = expanded[:max_target]
        if stats:
            stats["after"] = len(expanded)
        return expanded, stats

    def _collapse_to_single_span(
        self,
        boxes: list[list[int]],
        frame_w: int,
        frame_h: int,
    ) -> tuple[list[list[int]], dict | None]:
        if not boxes:
            return boxes, None

        span_left = min(b[0] for b in boxes)
        span_top = min(b[1] for b in boxes)
        span_right = max(b[2] for b in boxes)
        span_bottom = max(b[3] for b in boxes)

        horizontal_tier = "raw"
        frame_w_safe = max(1, int(frame_w))
        union_width = max(0, span_right - span_left)
        union_ratio = float(union_width) / float(frame_w_safe)

        target_x1 = span_left
        target_x2 = span_right

        target_ratio = min(1.0, max(_VN_SPAN_TIER_A_MIN, _VN_SPAN_TIER_A_TARGET))
        if union_ratio >= _VN_SPAN_TIER_B_MIN:
            target_x1 = 0
            target_x2 = frame_w_safe
            horizontal_tier = "tier_b_full"
        elif union_ratio >= _VN_SPAN_TIER_A_MIN:
            target_x1 = 0
            target_x2 = max(1, int(round(target_ratio * frame_w_safe)))
            horizontal_tier = "tier_a_wide"
        elif union_ratio < _VN_SPAN_TIER_A_MIN:
            horizontal_tier = "tier_c_raw"

        span_left = max(0, int(target_x1))
        span_top = max(0, int(span_top))
        span_right = min(frame_w_safe, int(target_x2))
        span_bottom = min(frame_h, int(span_bottom))

        best_box = max(
            boxes,
            key=lambda b: float(b[4]) if len(b) > 4 and isinstance(b[4], (int, float)) else 0.0,
        )
        extras = list(best_box[4:])
        if extras and isinstance(extras[-1], dict):
            extras[-1] = dict(extras[-1])

        collapsed = [span_left, span_top, span_right, span_bottom, *extras]
        self._set_box_flag(collapsed, _PRUNE_SINGLE_SPAN_FLAG)
        self._dbg(
            f"[SingleSpan] collapsed {len(boxes)} boxes -> span {[span_left, span_top, span_right, span_bottom]} "
            f"union_ratio={union_ratio:.3f} tier={horizontal_tier}"
        )
        meta = {
            "single_span": True,
            "span_before": len(boxes),
            "span_box": [span_left, span_top, span_right, span_bottom],
            "span_union_ratio": union_ratio,
            "span_horizontal_tier": horizontal_tier,
        }
        return [collapsed], meta

    def _dedupe_split_segments(self, boxes: list[list[int]], overlap_threshold: float = 0.7) -> list[list[int]]:
        if not boxes:
            return boxes

        deduped: list[list[int]] = []
        for box in sorted(boxes, key=lambda b: ((b[1] + b[3]) * 0.5, b[0])):
            replaced = False
            for idx, existing in enumerate(deduped):
                if not self._rows_overlap(existing, box):
                    continue
                overlap = self._horizontal_overlap_ratio(existing, box)
                if overlap >= overlap_threshold:
                    deduped[idx] = self._prefer_by_width_score(existing, box)
                    replaced = True
                    break
            if not replaced:
                deduped.append(box)
        return deduped

    def _rows_overlap(self, box_a: list[int], box_b: list[int]) -> bool:
        ay = (float(box_a[1]) + float(box_a[3])) * 0.5
        by = (float(box_b[1]) + float(box_b[3])) * 0.5
        return abs(ay - by) <= max(1.0, float(_PRUNE_DEDUP_COLLAPSE_Y_TOL))

    @staticmethod
    def _horizontal_overlap_ratio(box_a: list[int], box_b: list[int]) -> float:
        overlap_start = max(box_a[0], box_b[0])
        overlap_end = min(box_a[2], box_b[2])
        overlap = max(0, overlap_end - overlap_start)
        min_width = max(1, min(box_a[2] - box_a[0], box_b[2] - box_b[0]))
        return overlap / float(min_width)

    def _prefer_by_width_score(self, box_a: list[int], box_b: list[int]) -> list[int]:
        width_a = max(1, box_a[2] - box_a[0])
        width_b = max(1, box_b[2] - box_b[0])
        if width_a > width_b:
            return list(box_a)
        if width_b > width_a:
            return list(box_b)

        score_a = float(box_a[4]) if len(box_a) > 4 else float("-inf")
        score_b = float(box_b[4]) if len(box_b) > 4 else float("-inf")
        return list(box_a if score_a >= score_b else box_b)

    def _reduce_box_count(self, boxes: list[list[int]], target: int) -> tuple[list[list[int]], dict | None]:
        before = len(boxes)
        tolerance = max(1.0, float(_PRUNE_DEDUP_CLAMP_GAP))
        iterations = 0
        reduced = sorted(boxes, key=lambda b: ((b[1] + b[3]) * 0.5, b[0]))

        while len(reduced) > target and iterations < 5:
            reduced, merged_any = self._merge_neighbor_pairs(reduced, tolerance)
            if not merged_any:
                break
            tolerance *= 1.5
            iterations += 1

        if len(reduced) > target:
            reduced = reduced[:target]

        if before == len(reduced):
            return reduced, None

        return reduced, {
            "before": before,
            "after": len(reduced),
            "gap": tolerance,
        }

    def _merge_neighbor_pairs(
        self, boxes: list[list[int]], tolerance: float
    ) -> tuple[list[list[int]], bool]:
        merged: list[list[int]] = []
        merged_any = False
        i = 0
        while i < len(boxes):
            current = boxes[i]
            if i + 1 < len(boxes):
                nxt = boxes[i + 1]
                if self._boxes_can_merge(current, nxt, tolerance):
                    merged_any = True
                    merged_box = [
                        min(current[0], nxt[0]),
                        min(current[1], nxt[1]),
                        max(current[2], nxt[2]),
                        max(current[3], nxt[3]),
                    ]
                    extras = self._select_box_extras(current, nxt)
                    if extras:
                        merged_box.extend(extras)
                    merged.append(merged_box)
                    i += 2
                    continue
            merged.append(current)
            i += 1
        return merged, merged_any

    def _boxes_can_merge(self, box_a: list[int], box_b: list[int], tolerance: float) -> bool:
        ay = (box_a[1] + box_a[3]) * 0.5
        by = (box_b[1] + box_b[3]) * 0.5
        if abs(ay - by) > max(1.0, float(_PRUNE_DEDUP_COLLAPSE_Y_TOL)):
            return False
        ax = (box_a[0] + box_a[2]) * 0.5
        bx = (box_b[0] + box_b[2]) * 0.5
        if abs(ax - bx) > tolerance:
            return False
        return True

    @staticmethod
    def _select_box_extras(box_a: list[int], box_b: list[int]) -> list:
        extras_a = box_a[4:] if len(box_a) > 4 else []
        extras_b = box_b[4:] if len(box_b) > 4 else []
        if not extras_a and not extras_b:
            return []
        if extras_a and not extras_b:
            return list(extras_a)
        if extras_b and not extras_a:
            return list(extras_b)
        try:
            score_a = float(extras_a[0])
            score_b = float(extras_b[0])
            return list(extras_a if score_a >= score_b else extras_b)
        except (TypeError, ValueError):
            return list(extras_a)

    @staticmethod
    def _box_iou(box_a: list[int], box_b: list[int]) -> float:
        ax1, ay1, ax2, ay2 = box_a[:4]
        bx1, by1, bx2, by2 = box_b[:4]

        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)

        inter_w = max(0, inter_x2 - inter_x1)
        inter_h = max(0, inter_y2 - inter_y1)
        inter_area = inter_w * inter_h

        area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
        area_b = max(0, bx2 - bx1) * max(0, by2 - by1)

        denom = area_a + area_b - inter_area
        if denom <= 0:
            return 0.0
        return inter_area / float(denom)

    @staticmethod
    def _boxes_horizontally_close(box_a: list[int], box_b: list[int]) -> bool:
        ax1, ay1, ax2, ay2 = box_a[:4]
        bx1, by1, bx2, by2 = box_b[:4]

        aw = max(0.0, float(ax2 - ax1))
        bw = max(0.0, float(bx2 - bx1))
        ah = max(0.0, float(ay2 - ay1))
        bh = max(0.0, float(by2 - by1))

        if aw <= 0.0 or bw <= 0.0 or ah <= 0.0 or bh <= 0.0:
            return False

        acx = (float(ax1) + float(ax2)) * 0.5
        bcx = (float(bx1) + float(bx2)) * 0.5

        return (
            abs(acx - bcx) <= _PRUNE_DEDUP_CENTER_TOL
            and abs(aw - bw) <= _PRUNE_DEDUP_WIDTH_TOL
            and abs(ah - bh) <= _PRUNE_DEDUP_HEIGHT_TOL
        )

    def _estimate_box_density(self, image: np.ndarray, box: tuple[float, float, float, float], area_pixels: int) -> float:
        if area_pixels < _PRUNE_MIN_DENSITY_PIXELS:
            return 0.0
        crop = crop_box(image, box)
        if crop is None or crop.size == 0:
            return -10.0
        if crop.ndim == 3 and crop.shape[2] == 3:
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        elif crop.ndim == 3 and crop.shape[2] == 4:
            gray = cv2.cvtColor(crop, cv2.COLOR_BGRA2GRAY)
        else:
            gray = crop if crop.ndim == 2 else cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        ink_pixels = int(
            max(
                np.count_nonzero(gray < 50),
                np.count_nonzero(gray > 200),
            )
        )
        total_pixels = gray.size
        if total_pixels <= 0 or ink_pixels <= 0:
            return -10.0
        ink_ratio = ink_pixels / float(total_pixels)
        return float(math.log10(max(ink_ratio, 1e-6)))

    def _merge_horizontal_boxes(self, boxes: list, y_tol: int) -> list[list[int]]:
        if not boxes:
            return []

        sorted_boxes = sorted(boxes, key=lambda b: (float(b[1] + b[3]) * 0.5, float(b[0])))
        groups: list[list[list[float]]] = []

        for box in sorted_boxes:
            cy = (float(box[1]) + float(box[3])) * 0.5
            placed = False
            for group in groups:
                g_cy = sum((float(b[1]) + float(b[3])) * 0.5 for b in group) / len(group)
                if abs(cy - g_cy) <= y_tol:
                    group.append(box)
                    placed = True
                    break
            if not placed:
                groups.append([box])

        merged: list[list[int]] = []
        for group in groups:
            x1 = min(float(b[0]) for b in group)
            y1 = min(float(b[1]) for b in group)
            x2 = max(float(b[2]) for b in group)
            y2 = max(float(b[3]) for b in group)
            merged.append([int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))])

        merged.sort(key=lambda b: (b[1], b[0]))
        return merged

    def _sort_paddle_boxes(self, boxes):
        """
        Sort simple rectangular boxes [x1, y1, x2, y2]
        by top-most Y, then left-most X.
        """
        return sorted(boxes, key=lambda b: (b[1], b[0]))

    async def _recognize_box_groups(self, image: np.ndarray, boxes: list[list[int]], expand_for_recognition: bool = True) -> tuple[dict, dict]:
        if not boxes:
            return {"text": "", "confidence": 0.0}, {"normalized": 0, "trimmed": 0, "padded": 0, "boosted": 0}

        logger.debug("OCR: starting recognition for %d boxes", len(boxes))

        h, w = image.shape[:2]
        texts: list[str] = []
        confidences: list[float] = []

        logger.debug(f"[PaddleDebug] Raw boxes before sort: {boxes}")
        boxes = self._sort_paddle_boxes(boxes)
        if len(boxes) > 16:
            boxes = boxes[:16]
            self._dbg(f"[RecognizeCap] limiting to {len(boxes)} boxes for recognition")
        self._dbg(f"[Recognize] Sorted boxes: {boxes}")
        logger.debug(f"[PaddleDebug] Boxes after sort: {boxes}")
        logger.debug("OCR: sorted boxes = %s", boxes)
        rec_stats = {"normalized": 0, "trimmed": 0, "padded": 0, "boosted": 0}

        for idx, box in enumerate(boxes):
            skip_normalize = self._should_skip_normalize(box)
            normalize_meta: dict[str, object] = {"trimmed": False, "padded": False, "changed": False}
            box_to_use = box
            if _TRIM_PAD_ENABLED and not skip_normalize:
                norm_box, normalize_meta = self._normalize_crop(image, box, w, h)
                box_to_use = norm_box
                if normalize_meta.get("changed"):
                    self._dbg(
                        f"[Normalize] box={box} trimmed={normalize_meta.get('trimmed')} "
                        f"padded={normalize_meta.get('padded')} final={norm_box}"
                    )
            elif skip_normalize:
                self._dbg(f"[NormalizeSkip] synthetic span -> {box[:4]}")

            if expand_for_recognition:
                norm = self._normalize_box(box_to_use, w, h)
                if norm is None:
                    continue
                expanded = self._expand_box_for_recognition(norm, w, h)
                if expanded is None:
                    continue
                x1, y1, x2, y2 = expanded
                logger.debug("OCR: processing box %s", (x1, y1, x2, y2))
                self._dbg(f"[Crop] {(x1, y1, x2, y2)} size={(x2-x1)}x{(y2-y1)}")
                bw = x2 - x1
                bh = y2 - y1
                crop = image[y1:y2, x1:x2].copy()
                logger.debug(f"[PaddleDebug] Crop box: {(x1, y1, x2, y2)}")
            else:
                # Web parity crop semantics (Canvas drawImage-style):
                # keep float box coords, round width/height, then sample.
                x1 = max(0.0, min(float(w), float(box[0])))
                y1 = max(0.0, min(float(h), float(box[1])))
                x2 = max(0.0, min(float(w), float(box[2])))
                y2 = max(0.0, min(float(h), float(box[3])))
                logger.debug("OCR: processing box %s", (x1, y1, x2, y2))
                self._dbg(f"[Crop] {(x1, y1, x2, y2)} size={(x2-x1)}x{(y2-y1)}")
                bw = x2 - x1
                bh = y2 - y1
                crop = image[y1:y2, x1:x2].copy()
                logger.debug("[Rec] crop=%dx%d (expand=%s)", crop.shape[1] if crop is not None else 0, crop.shape[0] if crop is not None else 0, expand_for_recognition)
                if bw <= 0.0 or bh <= 0.0:
                    continue

                src_w = max(1, int(round(bw)))
                src_h = max(1, int(round(bh)))
                dst_w = max(4, int(round(bw)))
                dst_h = max(4, int(round(bh)))

                cx = x1 + (src_w * 0.5)
                cy = y1 + (src_h * 0.5)
                crop = cv2.getRectSubPix(image, (src_w, src_h), (cx, cy))
                if crop is None or crop.size == 0:
                    continue
                if _REC_PAD_PX > 0:
                    pad = _REC_PAD_PX
                    y_start = max(0, int(math.floor(y1)) - pad)
                    y_end = min(h, int(math.ceil(y2)) + pad)
                    x_start = max(0, int(math.floor(x1)) - pad)
                    x_end = min(w, int(math.ceil(x2)) + pad)
                    crop = image[y_start:y_end, x_start:x_end].copy()
                logger.debug("[Rec] crop=%dx%d (expand=%s)", crop.shape[1] if crop is not None else 0, crop.shape[0] if crop is not None else 0, expand_for_recognition)
                if dst_w != src_w or dst_h != src_h:
                    crop = cv2.resize(crop, (dst_w, dst_h), interpolation=cv2.INTER_LINEAR)

            if os.getenv("DESKTOCR_SAVE_CROPS", "0") == "1" and crop is not None and crop.size > 0:
                global _CROP_SAVE_COUNTER
                _CROP_SAVE_COUNTER += 1
                os.makedirs("debug_crops", exist_ok=True)
                crop_path = os.path.join(
                    "debug_crops",
                    f"crop_{_CROP_SAVE_COUNTER}_{int(round(x1))}_{int(round(y1))}.png",
                )
                try:
                    cv2.imwrite(crop_path, crop)
                except Exception as exc:
                    self._dbg(f"[CropSaveError] {exc}")

            logger.debug("OCR: crop size = %dx%d", bw, bh)
            boost_candidate = False
            if _TRIM_PAD_BOOST_ENABLED:
                boost_candidate = self._should_mark_boost(
                    image,
                    box_to_use,
                    w,
                    h,
                    normalize_meta=normalize_meta,
                    box_index=idx,
                )
                if boost_candidate:
                    self._dbg(
                        f"[BoostCandidate] box={box_to_use} area_ratio={self._box_area_ratio(box_to_use, w, h):.6f}"
                    )

            res = await self._current_instance.recognize(crop)
            text = res.get("text", "").strip()
            raw_conf = float(res.get("confidence", 0.0) or 0.0)
            conf = math.sqrt(max(raw_conf, 1e-3))
            if text:
                total_chars = len(text)
                if total_chars > 0:
                    jp_chars = score_japanese_density(text)
                    jp_ratio = float(jp_chars) / float(total_chars)
                    if jp_chars == 0:
                        self._dbg(f"[RecSkip] No JP chars -> '{text}'")
                        continue
                    if jp_ratio < 0.30:
                        self._dbg(f"[RecKeep] Low density but has JP chars ({jp_ratio:.2f}) -> '{text}'")
            self._dbg(f"[Rec] '{text}' conf={conf}")
            logger.debug("[RecResult] text='%s' conf=%.2f", text, conf)
            logger.debug("OCR: recognized text = '%s' (confidence=%s)", text, conf)
            if text:
                logger.debug(f"[PaddleDebug] Recognized: '{text}' conf={conf}")
                texts.append(text)
                confidences.append(conf)

            if normalize_meta.get("trimmed"):
                rec_stats["trimmed"] += 1
            if normalize_meta.get("padded"):
                rec_stats["padded"] += 1
            if normalize_meta.get("changed"):
                rec_stats["normalized"] += 1
            if boost_candidate:
                rec_stats["boosted"] += 1

        final_text = "\n".join(texts) if texts else ""
        self._dbg(f"[Final] {final_text}")
        logger.debug(f"[PaddleDebug] Final merged text:\n{final_text}")
        avg_conf = float(sum(confidences) / len(confidences)) if confidences else 0.0
        return {"text": final_text, "confidence": avg_conf}, rec_stats

    def _normalize_crop(self, image: np.ndarray, box: list[int], w: int, h: int) -> tuple[list[int], dict]:
        if not _TRIM_PAD_ENABLED:
            return box, {"trimmed": False, "padded": False, "changed": False}

        normalized = self._normalize_box(box, w, h)
        if normalized is None:
            normalized = (box[0], box[1], box[2], box[3])
        x1, y1, x2, y2 = normalized
        trimmed = False
        padded = False

        crop = crop_box(image, (x1, y1, x2, y2))
        height = y2 - y1
        if crop is not None and crop.size > 0 and height > 0:
            if crop.ndim == 3:
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            else:
                gray = crop
            ink = (gray < 235).astype(np.uint8)
            projection = ink.sum(axis=1)
            max_proj = projection.max(initial=0)
            if max_proj > 0:
                thresh = max_proj * _TRIM_PAD_PROJ_THRESH
                active = np.where(projection >= thresh)[0]
                if active.size > 0:
                    new_y1 = y1 + int(active[0])
                    new_y2 = y1 + int(active[-1]) + 1
                    if (new_y2 - new_y1) >= _PRUNE_MIN_BOX_HEIGHT:
                        y1, y2 = new_y1, new_y2
                        trimmed = True

        if _TRIM_PAD_MARGIN > 0:
            if x1 > 0 or y1 > 0 or x2 < w or y2 < h:
                x1 = max(0, x1 - _TRIM_PAD_MARGIN)
                y1 = max(0, y1 - _TRIM_PAD_MARGIN)
                x2 = min(w, x2 + _TRIM_PAD_MARGIN)
                y2 = min(h, y2 + _TRIM_PAD_MARGIN)
                padded = True

        width = max(_PRUNE_MIN_BOX_WIDTH, x2 - x1)
        height = max(_PRUNE_MIN_BOX_HEIGHT, y2 - y1)
        x2 = min(w, x1 + width)
        y2 = min(h, y1 + height)

        changed = trimmed or padded or (x1 != box[0] or y1 != box[1] or x2 != box[2] or y2 != box[3])
        return [x1, y1, x2, y2] + box[4:], {
            "trimmed": trimmed,
            "padded": padded,
            "changed": changed,
        }

    def _box_area_ratio(self, box: list[int], w: int, h: int) -> float:
        bw = max(0, box[2] - box[0])
        bh = max(0, box[3] - box[1])
        return (bw * bh) / float(max(1, w * h))

    def _should_mark_boost(
        self,
        image: np.ndarray | None,
        box: list[int],
        w: int,
        h: int,
        normalize_meta: dict[str, object] | None = None,
        box_index: int | None = None,
    ) -> bool:
        area_ratio = self._box_area_ratio(box, w, h)
        width = max(1, box[2] - box[0])
        height = max(1, box[3] - box[1])
        aspect = width / float(height)
        score = float(box[4]) if len(box) > 4 else None

        cond_area = 0.01 <= area_ratio <= 0.50
        cond_aspect = aspect <= 25.0

        density_log = None
        area_pixels = width * height
        if image is not None and area_pixels > 0:
            density_log = self._estimate_box_density(image, (box[0], box[1], box[2], box[3]), area_pixels)

        cond_density = density_log is None or density_log >= _PRUNE_DENSITY_LOG_THRESHOLD
        cond_conf = score is None or score >= _PRUNE_MIN_SCORE

        trimmed = bool(normalize_meta.get("trimmed")) if normalize_meta else False
        padded = bool(normalize_meta.get("padded")) if normalize_meta else False

        boost_ready = cond_area and cond_aspect and cond_density and cond_conf

        density_str = f"{density_log:.6f}" if density_log is not None else "n/a"
        score_str = f"{score:.3f}" if score is not None else "n/a"
        idx_str = box_index if box_index is not None else "-"
        boost_msg = (
            f"[BoostCheck] idx={idx_str} area={area_ratio:.6f} density={density_str} score={score_str} "
            f"trimmed={trimmed} padded={padded} size={width}x{height} "
            f"cond_area={cond_area} cond_aspect={cond_aspect} cond_density={cond_density} "
            f"cond_conf={cond_conf} -> {boost_ready}"
        )
        self._dbg(boost_msg)

        return boost_ready

    def _should_trigger_fallback(self, primary: dict, merged_boxes: list[list[int]], frame_w: int) -> bool:
        text = (primary.get("text", "") or "").strip()
        jp_chars = score_japanese_density(text)

        if not merged_boxes:
            return True
        if len(merged_boxes) > 8:
            return True
        if jp_chars < MIN_PRIMARY_JP_CHARS:
            return True

        widest = max((b[2] - b[0]) for b in merged_boxes)
        if widest < int(frame_w * 0.35):
            return True

        for b in merged_boxes:
            bw = b[2] - b[0]
            bh = b[3] - b[1]
            if bh <= 0:
                continue
            aspect = bw / bh
            if aspect > 40.0 or aspect < 1.0:
                return True

        return False

    def _extract_dynamic_bands(self, image: np.ndarray) -> list[tuple[int, int]]:
        h, _w = image.shape[:2]
        if h < 8:
            return []

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        energy = np.abs(grad_x).sum(axis=1)
        energy = cv2.GaussianBlur(energy.reshape(-1, 1), (1, 9), 0).reshape(-1)

        thresh = float(np.mean(energy) + 0.45 * np.std(energy))
        active = energy > thresh

        bands: list[tuple[int, int, float]] = []
        start = None
        for i, val in enumerate(active):
            if val and start is None:
                start = i
            elif not val and start is not None:
                end = i - 1
                if (end - start + 1) >= 8:
                    band_score = float(np.sum(energy[start:end + 1]))
                    bands.append((start, end, band_score))
                start = None
        if start is not None:
            end = len(active) - 1
            if (end - start + 1) >= 8:
                band_score = float(np.sum(energy[start:end + 1]))
                bands.append((start, end, band_score))

        if not bands:
            return []

        bands.sort(key=lambda x: x[2], reverse=True)
        top = bands[:MAX_FALLBACK_BANDS]
        top_sorted = sorted(top, key=lambda x: x[0])

        out: list[tuple[int, int]] = []
        for y1, y2, _score in top_sorted:
            margin = 6
            yy1 = max(0, y1 - margin)
            yy2 = min(h, y2 + 1 + margin)
            if yy2 - yy1 >= 8:
                out.append((yy1, yy2))
        return out

    async def _recognize_dynamic_bands(self, image: np.ndarray) -> dict:
        bands = self._extract_dynamic_bands(image)
        if not bands:
            return {"text": "", "confidence": 0.0}

        texts: list[str] = []
        confidences: list[float] = []
        for y1, y2 in bands:
            crop = image[y1:y2, :].copy()
            bh, bw = crop.shape[:2]

            band_detected = await self._current_instance.detect(crop)
            band_boxes = self._filter_boxes(band_detected, bw, bh)
            band_merged = self._merge_horizontal_boxes(band_boxes, y_tol=max(4, int(bh * 0.18)))
            detected_res, _band_stats = await self._recognize_box_groups(crop, band_merged)

            full_res = await self._current_instance.recognize(crop)
            best_band = self._pick_best_candidate(
                self._score_candidate(detected_res, source="band_detect"),
                self._score_candidate(full_res, source="band_full"),
            )
            text = best_band.get("text", "").strip()
            conf = float(best_band.get("confidence", 0.0) or 0.0)
            if text:
                logging.info(f"[PaddleDebug] Recognized: '{text}' conf={conf}")
                texts.append(text)
                confidences.append(conf)

        final_text = "\n".join(texts)
        avg_conf = float(sum(confidences) / len(confidences)) if confidences else 0.0
        return {"text": final_text, "confidence": avg_conf}

    def _score_candidate(self, candidate: dict, source: str) -> dict:
        text = (candidate.get("text", "") or "").strip()
        conf = float(candidate.get("confidence", 0.0) or 0.0)
        if not text:
            return {
                "source": source,
                "text": "",
                "confidence": conf,
                "jp_chars": 0,
                "jp_ratio": 0.0,
                "eligible": False,
            }

        jp_chars = int(score_japanese_density(text))
        jp_ratio = float(jp_chars / len(text)) if len(text) > 0 else 0.0
        eligible = jp_ratio >= MIN_CANDIDATE_JP_RATIO and jp_chars >= MIN_CANDIDATE_JP_CHARS

        return {
            "source": source,
            "text": text,
            "confidence": conf,
            "jp_chars": jp_chars,
            "jp_ratio": jp_ratio,
            "eligible": eligible,
        }

    def _pick_best_candidate(self, primary: dict, fallback: dict) -> dict:
        candidates = [primary, fallback]
        eligible = [c for c in candidates if c.get("eligible") and c.get("text")]

        def _score(c: dict) -> tuple:
            return (
                len(c.get("text", "")),
                int(c.get("jp_chars", 0)),
                float(c.get("jp_ratio", 0.0)),
            )

        if eligible:
            return max(eligible, key=_score)

        with_text = [c for c in candidates if c.get("text")]
        if with_text:
            return max(with_text, key=_score)

        return {
            "source": "none",
            "text": "",
            "confidence": 0.0,
            "jp_chars": 0,
            "jp_ratio": 0.0,
            "eligible": False,
        }

    def _fallback_is_meaningfully_better(self, primary: dict, fallback: dict) -> bool:
        if not fallback.get("text"):
            return False
        if not primary.get("text"):
            return True

        p_jp = int(primary.get("jp_chars", 0))
        f_jp = int(fallback.get("jp_chars", 0))
        p_len = len(primary.get("text", ""))
        f_len = len(fallback.get("text", ""))
        p_ratio = float(primary.get("jp_ratio", 0.0))
        f_ratio = float(fallback.get("jp_ratio", 0.0))

        if f_jp >= (p_jp + MIN_FALLBACK_GAIN_JP_CHARS):
            return True
        if f_len >= (p_len + MIN_FALLBACK_GAIN_TEXT_CHARS) and f_ratio >= p_ratio:
            return True
        return False

    async def preload_silently(self, engine_id: str):
        resolved_engine_id = self._resolve_engine_id(engine_id)
        if resolved_engine_id not in self._engines:
            logger.error(f"Unknown engine '{engine_id}' for silent preload.")
            return
            
        async def _silent_worker():
            try:
                await self.get_or_load_engine(resolved_engine_id)
            except Exception as e:
                logger.warning(f"Background preload failed for '{resolved_engine_id}': {e}")
                
        asyncio.create_task(_silent_worker())

    async def dispose_all(self):
        for engine_id, meta in self._engines.items():
            instance = meta["instance"]
            if instance and hasattr(instance, "dispose"):
                try:
                    await instance.dispose()
                except Exception as e:
                    logger.warning(f"Error disposing engine '{engine_id}': {e}")
                    
            meta["instance"] = None
            meta["state"] = "not_loaded"
            meta["task"] = None
            
        self._current_id = None
        self._current_instance = None
        logger.info("All engines have been disposed.")

    @property
    def is_ready(self) -> bool:
        if self._current_id is None or self._current_instance is None:
            return False
        return self._engines[self._current_id]["state"] == "ready"

    @property
    def current_id(self) -> str | None:
        return self._current_id

    async def _load_windows_ocr(self):
        try:
            from core.windows_ocr import WindowsOCR
        except Exception as e:
            reason = f"windows_ocr import failed: {e}"
            logger.warning(reason)
            return UnavailableEngine("windows_ocr", reason)

        try:
            engine = WindowsOCR()
            await engine.load()
        except Exception as e:
            reason = f"windows_ocr init failed: {e}"
            logger.warning(reason)
            return UnavailableEngine("windows_ocr", reason)

        if not getattr(engine, "available", False):
            reason = "windows_ocr unavailable (Japanese language pack or runtime prerequisites missing)"
            logger.warning(reason)
            return UnavailableEngine("windows_ocr", reason)

        return engine

    async def _load_easyocr(self):
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, __import__, "easyocr")
        except Exception:
            reason = "easyocr dependency missing; install easyocr to enable this engine"
            logger.warning(reason)
            return UnavailableEngine("easyocr", reason)

        engine = EasyOCREngine()
        await engine.load()
        return engine
