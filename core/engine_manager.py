import asyncio
import logging
import os
import math
import cv2
import numpy as np

from core.ocr_engine import PaddleOCR
from core.tensor_utils import PAD_LEFT, PAD_RIGHT, PAD_TOP, PAD_BOTTOM, preprocess_paddle_slice
from logic.validator import clean_ocr_output, is_valid_japanese, score_japanese_density

logger = logging.getLogger(__name__)

MIN_PRIMARY_JP_CHARS = 3
MIN_CANDIDATE_JP_RATIO = 0.30
MIN_CANDIDATE_JP_CHARS = 3
MAX_FALLBACK_BANDS = 2
MIN_FALLBACK_GAIN_JP_CHARS = 2
MIN_FALLBACK_GAIN_TEXT_CHARS = 3


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
    def __init__(self, models_dir: str, model_config: dict):
        self.models_dir = models_dir
        self.model_config = model_config
        self._telemetry = {
            "frames": 0,
            "boxes_raw": 0,
            "boxes_merged": 0,
            "fallback_hits": 0,
            "ocr_chars": 0,
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

    async def run_ocr(self, image: np.ndarray) -> dict:
        if not self._current_instance:
            logger.error("No active engine to run OCR.")
            return self._normalize_result("", 0.0, {"warning": "no_active_engine"})
            
        try:
            if self._current_id == "paddle":
                work_image = preprocess_paddle_slice(image)
                detected_boxes = await self._current_instance.detect(work_image)
                boxes_raw = len(detected_boxes)

                primary = await self._recognize_box_groups(work_image, detected_boxes, expand_for_recognition=False)
                final_text = (primary.get("text", "") or "").strip()
                final_conf = float(primary.get("confidence", 0.0) or 0.0)
                base_meta = {
                    "boxes_raw": boxes_raw,
                    "boxes_merged": 0,
                    "fallback_used": False,
                    "ocr_chars": len(final_text),
                }
            else:
                rec = await self._current_instance.recognize(image)
                final_text = (rec.get("text", "") or "").strip()
                final_conf = float(rec.get("confidence", 0.0) or 0.0)
                base_meta = rec.get("meta", {}) if isinstance(rec, dict) else {}

            final_text, validator_meta = self._apply_validator_assist(final_text, final_conf)
            combined_meta = dict(base_meta) if isinstance(base_meta, dict) else {}
            combined_meta.update(validator_meta)
            self._telemetry["frames"] += 1
            self._telemetry["boxes_raw"] += int(combined_meta.get("boxes_raw", 0) or 0)
            self._telemetry["boxes_merged"] += 0
            self._telemetry["fallback_hits"] += 0
            self._telemetry["ocr_chars"] += len(final_text)

            return self._normalize_result(final_text, final_conf, combined_meta)
        except Exception as e:
            logger.error(f"Error running OCR pipeline: {e}")
            return self._normalize_result("", 0.0, {"warning": str(e)})

    def _apply_validator_assist(self, text: str, confidence: float) -> tuple[str, dict]:
        if not text:
            return "", {"validator": {"enabled": not _validator_disabled(), "changed": False, "valid_hint": False, "jp_chars": 0}}

        if _validator_disabled():
            return text, {"validator": {"enabled": False, "changed": False, "valid_hint": True, "jp_chars": int(score_japanese_density(text))}}

        cleaned = clean_ocr_output(text)
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
        }
        if isinstance(meta, dict):
            normalized_meta.update(meta)
        return {
            "text": (text or "").strip(),
            "confidence": float(confidence or 0.0),
            "meta": normalized_meta,
        }

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

        # Keep web-style asymmetry while adding modest size-aware margin.
        pad_l = max(PAD_LEFT // 2, int(round(bw * 0.03)))
        pad_r = max(PAD_RIGHT // 2, int(round(bw * 0.02)))
        pad_t = max(PAD_TOP, int(round(bh * 0.18)))
        pad_b = max(PAD_BOTTOM, int(round(bh * 0.18)))

        ex1 = max(0, x1 - pad_l)
        ey1 = max(0, y1 - pad_t)
        ex2 = min(w, x2 + pad_r)
        ey2 = min(h, y2 + pad_b)

        if (ex2 - ex1) < 4 or (ey2 - ey1) < 4:
            return None
        return ex1, ey1, ex2, ey2

    def _filter_boxes(self, boxes: list, w: int, h: int) -> list[list[int]]:
        if not boxes:
            return []

        min_w = max(8, int(w * 0.015))
        min_h = max(8, int(h * 0.05))
        min_area = max(80, int(w * h * 0.00015))

        out: list[list[int]] = []
        for b in boxes:
            norm = self._normalize_box(b, w, h)
            if norm is None:
                continue
            x1, y1, x2, y2 = norm
            bw = x2 - x1
            bh = y2 - y1
            area = bw * bh
            if bw < min_w or bh < min_h or area < min_area:
                continue
            aspect = bw / bh if bh > 0 else 0.0
            if aspect < 0.5 or aspect > 45.0:
                continue
            out.append([x1, y1, x2, y2])

        return out

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

    async def _recognize_box_groups(self, image: np.ndarray, boxes: list[list[int]], expand_for_recognition: bool = True) -> dict:
        if not boxes:
            return {"text": "", "confidence": 0.0}

        h, w = image.shape[:2]
        texts: list[str] = []
        confidences: list[float] = []

        for box in boxes:
            if expand_for_recognition:
                norm = self._normalize_box(box, w, h)
                if norm is None:
                    continue
                expanded = self._expand_box_for_recognition(norm, w, h)
                if expanded is None:
                    continue
                x1, y1, x2, y2 = expanded
                crop = image[y1:y2, x1:x2].copy()
            else:
                # Web parity crop semantics (Canvas drawImage-style):
                # keep float box coords, round width/height, then sample.
                x1 = max(0.0, min(float(w), float(box[0])))
                y1 = max(0.0, min(float(h), float(box[1])))
                x2 = max(0.0, min(float(w), float(box[2])))
                y2 = max(0.0, min(float(h), float(box[3])))
                bw = x2 - x1
                bh = y2 - y1
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
                if dst_w != src_w or dst_h != src_h:
                    crop = cv2.resize(crop, (dst_w, dst_h), interpolation=cv2.INTER_LINEAR)

            res = await self._current_instance.recognize(crop)
            text = res.get("text", "").strip()
            conf = float(res.get("confidence", 0.0) or 0.0)
            if text:
                texts.append(text)
                confidences.append(conf)

        final_text = "\n".join(texts)
        avg_conf = float(sum(confidences) / len(confidences)) if confidences else 0.0
        return {"text": final_text, "confidence": avg_conf}

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
            detected_res = await self._recognize_box_groups(crop, band_merged)

            full_res = await self._current_instance.recognize(crop)
            best_band = self._pick_best_candidate(
                self._score_candidate(detected_res, source="band_detect"),
                self._score_candidate(full_res, source="band_full"),
            )
            text = best_band.get("text", "").strip()
            conf = float(best_band.get("confidence", 0.0) or 0.0)
            if text:
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
