import asyncio
import difflib
import logging
from typing import Optional

import cv2

from core.engine_manager import EngineManager
from core.capture import ScreenCapture
from logic.validator import clean_ocr_output_enhanced

try:
    from logic.google_vision_ocr import GoogleVisionOCR
except ImportError:  # pragma: no cover
    GoogleVisionOCR = None  # type: ignore

try:
    from logic.deepseek_validator import DeepSeekValidator
except ImportError:  # pragma: no cover
    DeepSeekValidator = None  # type: ignore

logger = logging.getLogger(__name__)

class CapturePipeline:
    def __init__(
        self,
        engine_manager: EngineManager,
        capture: ScreenCapture,
        openai_validator=None,
        google_vision: Optional["GoogleVisionOCR"] = None,
        deepseek_validator: Optional["DeepSeekValidator"] = None,
    ):
        self.engine_manager = engine_manager
        self.capture = capture
        self._openai_validator = openai_validator
        self._google_vision = google_vision
        self._deepseek_validator = deepseek_validator
        
        self.capture_generation = 0
        self.is_processing = False
        self._last_result = ""
        self._lock = asyncio.Lock()
        
        self._auto_task = None
        self._line_count: int = 1
        self._stats = {
            "frames": 0,
            "boxes_raw": 0,
            "boxes_merged": 0,
            "fallback_hits": 0,
            "chars_emitted": 0,
        }
        self._stats_log_every = 20

    def set_line_count(self, n: int) -> None:
        try:
            value = int(n)
        except (TypeError, ValueError):
            value = 1
        self._line_count = max(1, value)

    def invalidate_generation(self) -> None:
        """Bump generation counter so in-flight OCR results are discarded."""
        self.capture_generation += 1

    async def capture_once(self, *, line_count: int = 1) -> dict | None:
        """
        Captures a frame and processes it via the OCR engine.
        Returns {"text": str, "confidence": float} or None.
        """
        if self.is_processing:
            return None

        self.is_processing = True
        self.capture_generation += 1
        my_gen = self.capture_generation
        
        try:
            frame = await self.capture.get_frame()
            if frame is None:
                return None
                
            if self.capture_generation != my_gen:
                return None
                
            res = None
            if self._google_vision and self._google_vision.is_enabled():
                res = await self._run_google_vision(frame)

            if res is None:
                res = await self.engine_manager.run_ocr(frame, line_count=line_count)
            
            if self.capture_generation != my_gen:
                return None
                
            text = (res.get("text", "") or "").strip()
            text = clean_ocr_output_enhanced(text)
            meta = res.get("meta", {}) if isinstance(res, dict) else {}

            text, meta = await self._apply_ai_validators(text, meta)
            res["text"] = text
            res["meta"] = meta
            conf = res.get("confidence")
            res["confidence"] = conf if conf is not None else 0.0
            self._update_stats(meta)

            if not text:
                self._maybe_log_stats()
                return None

            self._last_result = text
            self._stats["chars_emitted"] += len(text)
            self._maybe_log_stats()
            if isinstance(res, dict):
                res["frame"] = frame.copy()
                return res

            return {
                "text": text,
                "confidence": conf if conf is not None else 0.0,
                "meta": meta,
                "frame": frame.copy(),
            }
            
        except Exception as e:
            logger.error(f"Error during capture_once: {e}")
            return None
        finally:
            self.is_processing = False

    async def _apply_ai_validators(self, text: str, meta: dict | None) -> tuple[str, dict]:
        if not text:
            return text, meta or {}

        meta = meta or {}
        original_text = text

        async def _run_validator(label: str, validator) -> dict | None:
            if not validator:
                return None
            if not hasattr(validator, "is_available"):
                return None
            try:
                available = await validator.is_available()  # type: ignore[func-returns-value]
            except Exception:  # pragma: no cover
                return None
            if not available:
                return None
            try:
                return await asyncio.wait_for(
                    validator.validate_and_fix(text),
                    timeout=5.0,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "[Pipeline] %s validator timed out — using unvalidated text",
                    label,
                )
                return None
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "[Pipeline] %s validator failed: %s", label, exc
                )
                return None

        ai_validators = [
            ("deepseek", self._deepseek_validator),
            ("openai", self._openai_validator),
        ]
        for label, validator in ai_validators:
            result = await _run_validator(label, validator)
            if not result:
                continue
            new_text = (result.get("text", "") or "").strip()
            if not new_text:
                continue
            meta["ai_validator"] = {
                "engine": result.get("source", "unknown"),
                "changed": new_text != original_text,
            }
            return clean_ocr_output_enhanced(new_text), meta

        meta.setdefault("ai_validator", {"engine": "deterministic", "changed": False})
        return text, meta

    async def _run_google_vision(self, frame) -> dict | None:
        try:
            success, encoded = cv2.imencode(".png", frame)
            if not success:
                return None
            text = await self._google_vision.ocr_image(encoded.tobytes())  # type: ignore[arg-type]
            if not text:
                return None
            return {
                "text": text,
                "confidence": None,
                "meta": {
                    "engine": "google_vision",
                    "cloud": True,
                    "boxes_raw": 0,
                    "boxes_merged": 0,
                },
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Google Vision OCR processing failed: %s", exc)
            return None

    async def run_auto(self, callback, interval_ms=500, stabilize_ms=800):
        """
        Auto-capture loop. Polls capture_once and triggers a callback upon successful stabilization.
        """
        self._auto_task = asyncio.current_task()
        interval = interval_ms / 1000.0
        stabilize = stabilize_ms / 1000.0
        
        try:
            while True:
                await asyncio.sleep(interval)
                
                res = await self.capture_once(line_count=self._line_count)
                if res is not None:
                    result_gen = self.capture_generation
                    # New valid result detected: wait for stabilization
                    await asyncio.sleep(stabilize)
                    # Only fire if no new capture happened during stabilization
                    if self.capture_generation == result_gen:
                        callback(res)
                    
        except asyncio.CancelledError:
            logger.info("Auto-capture loop cancelled.")
            pass

    def stop_auto(self):
        """
        Cancels the active auto-capture loop and resets states.
        """
        if self._auto_task:
            self._auto_task.cancel()
            self._auto_task = None
            
        self.is_processing = False

    def _is_near_duplicate(self, current: str, previous: str) -> bool:
        if not current or not previous:
            return False

        if current in previous or previous in current:
            if abs(len(current) - len(previous)) <= 2:
                return True

        ratio = difflib.SequenceMatcher(a=current, b=previous).ratio()
        return ratio >= 0.90

    def _update_stats(self, meta: dict) -> None:
        self._stats["frames"] += 1
        self._stats["boxes_raw"] += int(meta.get("boxes_raw", 0) or 0)
        self._stats["boxes_merged"] += int(meta.get("boxes_merged", 0) or 0)
        self._stats["fallback_hits"] += int(bool(meta.get("fallback_used", False)))

    def _maybe_log_stats(self) -> None:
        frames = self._stats["frames"]
        if frames <= 0 or (frames % self._stats_log_every) != 0:
            return

        fallback_rate = self._stats["fallback_hits"] / frames
        avg_chars = self._stats["chars_emitted"] / frames

        logger.info(
            "OCR stats | frames=%d | boxes_raw=%d | boxes_merged=%d | fallback_hits=%d | chars_emitted=%d | fallback_rate=%.2f | avg_chars=%.2f",
            frames,
            self._stats["boxes_raw"],
            self._stats["boxes_merged"],
            self._stats["fallback_hits"],
            self._stats["chars_emitted"],
            fallback_rate,
            avg_chars,
        )
