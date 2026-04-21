import asyncio
import difflib
import logging
from collections import Counter

from core.engine_manager import EngineManager
from core.capture import ScreenCapture
from logic.validator import score_japanese_density

logger = logging.getLogger(__name__)

class CapturePipeline:
    def __init__(self, engine_manager: EngineManager, capture: ScreenCapture):
        self.engine_manager = engine_manager
        self.capture = capture
        
        self.capture_generation = 0
        self.is_processing = False
        self._last_result = ""
        self._lock = asyncio.Lock()
        
        self._auto_task = None
        self.multi_pass_enabled = False
        self._stats = {
            "frames": 0,
            "boxes_raw": 0,
            "boxes_merged": 0,
            "fallback_hits": 0,
            "chars_emitted": 0,
        }
        self._stats_log_every = 20

    async def capture_once(self) -> dict | None:
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
                
            res = await self.engine_manager.run_ocr(frame)
            
            if self.capture_generation != my_gen:
                return None
                
            text = (res.get("text", "") or "").strip()
            conf = res.get("confidence")
            meta = res.get("meta", {}) if isinstance(res, dict) else {}
            self._update_stats(meta)

            if not text:
                self._maybe_log_stats()
                return None

            self._last_result = text
            self._stats["chars_emitted"] += len(text)
            self._maybe_log_stats()
            return {
                "text": text,
                "confidence": conf if conf is not None else 0.0,
                "meta": meta,
            }
            
        except Exception as e:
            logger.error(f"Error during capture_once: {e}")
            return None
        finally:
            self.is_processing = False

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
                
                res = await self.capture_once()
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

    async def _multi_pass(self, frame, my_gen) -> dict | None:
        """
        Execute OCR pass 5 times and perform voting on the output.
        """
        # TODO: multi-pass requires different preprocessing per pass to be meaningful.
        # Currently all 5 passes are identical (deterministic model).
        # Wire up vision.py preprocessing variants here when implemented.
        results = []
        for _ in range(5):
            res = await self.engine_manager.run_ocr(frame)
            if self.capture_generation != my_gen:
                return None
                
            results.append(res)
            
        return self._pick_best_result(results)

    def _pick_best_result(self, results: list) -> dict:
        """
        Selects the best result from a multi-pass execution array.
        """
        if not results:
            return {"text": "", "confidence": 0.0}

        counts = Counter(r.get("text", "") for r in results)
        
        # 1. Majority vote
        for text, count in counts.items():
            if count >= 3:
                # Return the first underlying result corresponding to the winning text
                for r in results:
                    if r.get("text", "") == text:
                        return r
                        
        # 2 + 3. Highest confidence and Weighted score fallback
        # Ported logic: evaluate weighted score directly returning the maximum
        best_weighted = results[0]
        best_score = -1.0
        
        for r in results:
            conf = r.get("confidence")
            if conf is None:
                conf = 0.0
                
            density = score_japanese_density(r.get("text", ""))
            
            score = conf * 0.7 + density * 0.3
            if score > best_score:
                best_score = score
                best_weighted = r
                
        return best_weighted

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
