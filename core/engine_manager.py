import asyncio
import logging
import numpy as np

from core.ocr_engine import PaddleOCR
from core.tensor_utils import crop_box

logger = logging.getLogger(__name__)

class EngineManager:
    def __init__(self, models_dir: str, model_config: dict):
        self.models_dir = models_dir
        self.model_config = model_config
        
        self._engines = {
            "server": {"instance": None, "state": "not_loaded", "task": None},
            "windows_ocr": {"instance": None, "state": "not_loaded", "task": None}
        }
        
        self._current_id = None
        self._current_instance = None
        self._switch_lock = asyncio.Lock()

    async def switch_engine(self, engine_id: str) -> bool:
        if engine_id not in self._engines:
            logger.error(f"Engine '{engine_id}' is not supported.")
            return False
            
        async with self._switch_lock:
            if self._current_id == engine_id and self._engines[engine_id]["state"] == "ready":
                return True
                
            try:
                instance = await self.get_or_load_engine(engine_id)
                self._current_id = engine_id
                self._current_instance = instance
                logger.info(f"Successfully switched to engine: {engine_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to switch to engine {engine_id}: {e}")
                return False

    async def get_or_load_engine(self, engine_id: str):
        meta = self._engines.get(engine_id)
        if not meta:
            raise ValueError(f"Unknown engine: {engine_id}")
            
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
                if engine_id == "server":
                    engine = PaddleOCR(self.models_dir, self.model_config)
                    await engine.load()
                elif engine_id == "windows_ocr":
                    engine = await self._load_windows_ocr()
                else:
                    raise ValueError(f"Unknown engine ID '{engine_id}'")
                    
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
            return {"text": "", "confidence": 0.0}
            
        try:
            boxes = await self._current_instance.detect(image)
            
            if not boxes:
                return {"text": "", "confidence": 0.0}
                
            texts = []
            confidences = []
            
            for box in boxes:
                # Direct numpy slice instead of crop_box. Boxes from detect()
                # are already padded in detection-space before coordinate scaling.
                x1, y1, x2, y2 = [int(round(v)) for v in box]
                h, w = image.shape[:2]
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w, x2), min(h, y2)
                if (x2 - x1) < 4 or (y2 - y1) < 4:
                    continue
                crop = image[y1:y2, x1:x2].copy()
                
                res = await self._current_instance.recognize(crop)
                text = res.get("text", "").strip()
                conf = res.get("confidence", 0.0)
                
                if text:
                    texts.append(text)
                    confidences.append(conf)
                        
            final_text = "\n".join(texts)
            avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
            
            return {"text": final_text, "confidence": avg_conf}
        except Exception as e:
            logger.error(f"Error running OCR pipeline: {e}")
            return {"text": "", "confidence": 0.0}

    async def preload_silently(self, engine_id: str):
        if engine_id not in self._engines:
            logger.error(f"Unknown engine '{engine_id}' for silent preload.")
            return
            
        async def _silent_worker():
            try:
                await self.get_or_load_engine(engine_id)
            except Exception as e:
                logger.warning(f"Background preload failed for '{engine_id}': {e}")
                
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
        raise NotImplementedError("Windows OCR engine is not implemented yet.")
