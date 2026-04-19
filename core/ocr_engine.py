import asyncio
import logging
import pathlib
import numpy as np
import onnxruntime as ort
import cv2

from core.tensor_utils import (
    image_to_det_tensor,
    image_to_rec_tensor,
    PAD_LEFT,
    PAD_RIGHT,
    PAD_TOP,
    PAD_BOTTOM,
    filter_noise_boxes,
)

logger = logging.getLogger(__name__)

class PaddleOCR:
    def __init__(self, models_dir: str, model_config: dict):
        self.models_dir = pathlib.Path(models_dir)
        self.model_config = model_config
        self.providers = ["DmlExecutionProvider", "CPUExecutionProvider"]

        self.det_session = None
        self.rec_session = None
        self.dict = []

        self._load_lock = asyncio.Lock()
        self._busy_lock = asyncio.Lock()
        self._warmed_up = False

    async def load(self):
        if self.det_session is not None and self.rec_session is not None:
            return self

        async with self._load_lock:
            # Re-check inside the lock to ensure idempotency
            if self.det_session is not None and self.rec_session is not None:
                return self

            try:
                dict_path = self.models_dir / self.model_config["dict"]
                logger.info(f"Loading dictionary from {dict_path}...")
                with open(dict_path, "r", encoding="utf-8") as f:
                    lines = f.read().split("\n")
                    self.dict = [line.strip() for line in lines]
                    if len(self.dict) > 0 and self.dict[-1] == "":
                        self.dict.pop()

                loop = asyncio.get_running_loop()

                det_path = str(self.models_dir / self.model_config["det"])
                logger.info(f"Initializing detection session with {det_path}...")
                self.det_session = await loop.run_in_executor(
                    None, lambda: ort.InferenceSession(det_path, providers=self.providers)
                )

                rec_path = str(self.models_dir / self.model_config["rec"])
                logger.info(f"Initializing recognition session with {rec_path}...")
                self.rec_session = await loop.run_in_executor(
                    None, lambda: ort.InferenceSession(rec_path, providers=self.providers)
                )

                logger.info("Warming up models...")
                await self.warm_up()
                
                logger.info("PaddleOCR engine loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load PaddleOCR models: {e}")
                raise

        return self

    async def warm_up(self):
        if self._warmed_up:
            return
            
        self._warmed_up = True

        if self.det_session is None or self.rec_session is None:
            return

        try:
            # Micro-yield
            await asyncio.sleep(0)

            loop = asyncio.get_running_loop()

            # Warm up detection
            det_shape = (1, 3, 960, 960)
            det_dummy = np.zeros(det_shape, dtype=np.float32)
            det_input_name = self.det_session.get_inputs()[0].name
            await loop.run_in_executor(None, self.det_session.run, None, {det_input_name: det_dummy})

            # Warm up recognition
            rec_shape = (1, 3, 48, 320)
            rec_dummy = np.zeros(rec_shape, dtype=np.float32)
            rec_input_name = self.rec_session.get_inputs()[0].name
            await loop.run_in_executor(None, self.rec_session.run, None, {rec_input_name: rec_dummy})

            logger.info("PaddleOCR warm-up complete")
        except Exception as e:
            logger.warning(f"PaddleOCR warm-up skipped (fallback or error): {e}")

    async def detect(self, image: np.ndarray) -> list:
        if self.det_session is None:
            return []

        try:
            h_orig, w_orig = image.shape[:2]

            tensor_data = image_to_det_tensor(image)
            input_name = self.det_session.get_inputs()[0].name

            loop = asyncio.get_running_loop()
            outputs = await loop.run_in_executor(None, self.det_session.run, None, {input_name: tensor_data})
            output_map = outputs[0]

            # Output dims mapping depending on batch size
            if len(output_map.shape) == 4:
                map_2d = output_map[0, 0, :, :]
            elif len(output_map.shape) == 3:
                map_2d = output_map[0, :, :]
            else:
                map_2d = output_map

            map_h, map_w = map_2d.shape

            # Threshold map at 0.3
            threshold = 0.3
            binary_map = (map_2d > threshold).astype(np.uint8)

            # Find connected components
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary_map, connectivity=8)

            boxes = []
            scale_x = w_orig / map_w
            scale_y = h_orig / map_h

            # Skip label 0 which is background
            for label in range(1, num_labels):
                x = stats[label, cv2.CC_STAT_LEFT]
                y = stats[label, cv2.CC_STAT_TOP]
                w = stats[label, cv2.CC_STAT_WIDTH]
                h = stats[label, cv2.CC_STAT_HEIGHT]

                min_x = x
                min_y = y
                max_x = x + w - 1
                max_y = y + h - 1

                p_min_x = max(0, min_x - PAD_LEFT)
                p_min_y = max(0, min_y - PAD_TOP)
                p_max_x = min(map_w, max_x + PAD_RIGHT + 1)
                p_max_y = min(map_h, max_y + PAD_BOTTOM + 1)

                x1 = p_min_x * scale_x
                y1 = p_min_y * scale_y
                x2 = p_max_x * scale_x
                y2 = p_max_y * scale_y

                boxes.append([x1, y1, x2, y2])

            filtered_boxes = filter_noise_boxes(boxes)
            return filtered_boxes
        except Exception as e:
            logger.error(f"PaddleOCR detection error: {e}")
            return []

    async def recognize(self, crop: np.ndarray) -> dict:
        if self.rec_session is None:
            return {"text": "", "confidence": 0.0}

        if self._busy_lock.locked():
            logger.warning("PaddleOCR: Inference skipped — session is busy.")
            return {"text": "", "confidence": 0.0}

        async with self._busy_lock:
            try:
                tensor_data = image_to_rec_tensor(crop)

                input_name = self.rec_session.get_inputs()[0].name
                loop = asyncio.get_running_loop()
                outputs = await loop.run_in_executor(None, self.rec_session.run, None, {input_name: tensor_data})

                logits = outputs[0]

                dims = logits.shape
                if len(dims) == 3:
                    batch, time_steps, num_classes = dims
                elif len(dims) == 2:
                    batch = 1
                    time_steps, num_classes = dims
                    logits = np.expand_dims(logits, axis=0)
                else:
                    return {"text": "", "confidence": 0.0}

                return self._ctc_greedy_decode(logits, [batch, time_steps, num_classes])
            except Exception as e:
                logger.error(f"PaddleOCR recognition error: {e}")
                return {"text": "", "confidence": 0.0}

    def _ctc_greedy_decode(self, logits: np.ndarray, dims: list) -> dict:
        try:
            batch, time_steps, num_classes = dims
            texts = []
            avg_confidences = []

            for b in range(batch):
                prev = -1
                chars = []
                max_probs = []

                for t in range(time_steps):
                    timestep_logits = logits[b, t, :]
                    exp_logits = np.exp(timestep_logits - np.max(timestep_logits))
                    probs = exp_logits / exp_logits.sum()
                    max_idx = int(np.argmax(probs))
                    max_val = float(probs[max_idx])
                    
                    max_probs.append(max_val)

                    if max_idx != 0 and max_idx != prev:
                        dict_idx = max_idx - 1
                        if 0 <= dict_idx < len(self.dict):
                            chars.append(self.dict[dict_idx])

                    prev = max_idx

                texts.append("".join(chars))
                conf = float(np.mean(max_probs)) if max_probs else 0.0
                avg_confidences.append(conf)

            return {"text": texts[0] if texts else "", "confidence": avg_confidences[0] if avg_confidences else 0.0}
        except Exception as e:
            logger.error(f"PaddleOCR CTC Decoding Error: {e}")
            return {"text": "", "confidence": 0.0}

    async def dispose(self):
        self.det_session = None
        self.rec_session = None
        self.dict = []
        self._warmed_up = False
