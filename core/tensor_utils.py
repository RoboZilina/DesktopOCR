import os

import cv2
import numpy as np

# Shared resources for zero-churn tensor conversion
# Pre-allocate once, reuse every frame — never allocate inside the hot path.
# NOTE: These globals rely on PaddleOCR's `_busy_lock` to serialize recognition
# calls. If we ever introduce true parallel Paddle passes, switch to per-call
# allocations (or guard the buffers with explicit synchronization).
DET_LIMIT_SIDE_LEN = int(os.getenv("DESKTOCR_DET_LIMIT_SIDE_LEN", "1024"))
import threading

DET_BUFFER = None
DET_BUFFER_SHAPE: tuple[int, int, int, int] | None = None
_det_buffer_lock = threading.Lock()
REC_BUFFER = np.zeros((1, 3, 48, 320), dtype=np.float32)

# Detection box padding (applied in detection-space BEFORE scaling to original coords)
PAD_LEFT = 20
PAD_RIGHT = 12
PAD_TOP = 12
PAD_BOTTOM = 12

MIN_BOX_AREA = 40 * 40

CLAHE_CLIP_LIMIT = 2.0
CLAHE_TILE_GRID_SIZE = (8, 8)
SHARPEN_KERNEL = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)


def trim_empty_vertical(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        return image
    # Web parity: trimEmptyVertical() removes only fully transparent rows.
    # Desktop frames are typically opaque BGR, so this is intentionally a no-op.
    if len(image.shape) < 3 or image.shape[2] < 4:
        return image

    alpha = image[:, :, 3]
    non_empty_rows = np.where(np.any(alpha != 0, axis=1))[0]
    if non_empty_rows.size == 0:
        return image

    top = int(non_empty_rows[0])
    bottom = int(non_empty_rows[-1]) + 1
    if bottom <= top:
        return image
    return image[top:bottom, :]


def pad_left(image: np.ndarray, px: int = 8) -> np.ndarray:
    if image is None or image.size == 0 or px <= 0:
        return image
    h, w = image.shape[:2]
    if image.ndim == 2:
        out = np.zeros((h, w + px), dtype=image.dtype)
    else:
        out = np.zeros((h, w + px, image.shape[2]), dtype=image.dtype)
    out[..., px:] = image
    return out


def boost_contrast(image: np.ndarray, alpha: float = 1.08) -> np.ndarray:
    if image is None or image.size == 0:
        return image
    return cv2.convertScaleAbs(image, alpha=alpha, beta=0)


def _ensure_bgr(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        return image
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image


def preprocess_paddle_slice(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        return image
    trimmed = trim_empty_vertical(image)
    work = _ensure_bgr(trimmed)
    work = pad_left(work, px=8)
    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=CLAHE_TILE_GRID_SIZE)
    enhanced = clahe.apply(gray)
    restored = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
    if os.getenv("DESKTOCR_SHARPEN", "0") == "1":
        return cv2.filter2D(restored, -1, SHARPEN_KERNEL)
    return restored


def preprocess_natural_slice(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        return image

    if len(image.shape) == 2:
        gray = image
    elif len(image.shape) == 3 and image.shape[2] == 1:
        gray = image[:, :, 0]
    elif len(image.shape) == 3 and image.shape[2] == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    elif len(image.shape) == 3 and image.shape[2] == 4:
        gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    else:
        return image

    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

def _ensure_det_buffer(height: int, width: int) -> np.ndarray:
    global DET_BUFFER, DET_BUFFER_SHAPE
    shape = (1, 3, height, width)
    with _det_buffer_lock:
        if DET_BUFFER is None or DET_BUFFER_SHAPE != shape:
            DET_BUFFER = np.zeros(shape, dtype=np.float32)
            DET_BUFFER_SHAPE = shape
        return DET_BUFFER


def _round_to_multiple(value: float, divisor: int = 32) -> int:
    if divisor <= 0:
        return int(round(value))
    units = max(1, int(np.ceil(float(value) / float(divisor))))
    return units * divisor


def _resize_with_limit(image: np.ndarray, limit_side_len: int) -> tuple[np.ndarray, int, int]:
    h, w = image.shape[:2]
    if h <= 0 or w <= 0:
        return image, h, w
    scale = 1.0
    max_side = max(h, w)
    if limit_side_len > 0 and max_side > limit_side_len:
        scale = limit_side_len / float(max_side)
    target_h = _round_to_multiple(max(32.0, h * scale))
    target_w = _round_to_multiple(max(32.0, w * scale))
    if limit_side_len > 0:
        target_h = min(limit_side_len, target_h)
        target_w = min(limit_side_len, target_w)
    if target_h == h and target_w == w:
        return image, h, w
    resized = cv2.resize(image, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
    return resized, target_h, target_w


def image_to_det_tensor(image: np.ndarray) -> tuple[np.ndarray, int, int]:
    """
    canvasToFloat32Tensor equivalent for detection.
    Resize while preserving aspect ratio, clamping the longest side to DET_LIMIT_SIDE_LEN.
    Returns (tensor, height, width).
    """
    if image is None or image.size == 0:
        return np.zeros((1, 3, 32, 32), dtype=np.float32), 32, 32
    source = _ensure_bgr(image)
    canvas, target_h, target_w = _resize_with_limit(source, DET_LIMIT_SIDE_LEN)

    # Normalize: (pixel/255 - 0.5) / 0.5
    img_float = canvas.astype(np.float32)
    img_float = (img_float / 255.0 - 0.5) / 0.5

    # HWC to CHW
    img_chw = img_float.transpose(2, 0, 1)

    # Write into DET_BUFFER in-place
    buffer = _ensure_det_buffer(target_h, target_w)
    buffer[0] = img_chw

    # Fallback for internal shared buffers (Legacy Copy logic)
    return buffer.copy(), target_h, target_w

def image_to_rec_tensor(image: np.ndarray) -> np.ndarray:
    """
    canvasToFloat32Tensor equivalent for recognition
    Preserve aspect ratio, max width/height
    """
    source = image
    target_h = 48
    max_w = 320
    h, w = source.shape[:2]

    # Scale to height=48 EXACTLY, preserve aspect ratio for width
    scale = target_h / h
    new_w = min(max_w, max(1, int(round(w * scale))))

    resized = cv2.resize(source, (new_w, target_h), interpolation=cv2.INTER_LINEAR)

    canvas = np.zeros((target_h, max_w, 3), dtype=np.uint8)
    canvas[:, :new_w] = resized

    # Normalize: same as above
    img_float = canvas.astype(np.float32)
    img_float = (img_float / 255.0 - 0.5) / 0.5

    
    # HWC to CHW
    img_chw = img_float.transpose(2, 0, 1)
    
    # Write into REC_BUFFER in-place
    REC_BUFFER[0] = img_chw
    
    # Keep fixed input shape (1, 3, 48, 320) with right-side black padding.
    # Variable-width tensors can destabilize decoding for this model family.
    return REC_BUFFER.copy()

def crop_box(image: np.ndarray, box: list) -> np.ndarray | None:
    """
    Crop a box from the original canvas
    box: [x1, y1, x2, y2] in original coordinates
    """
    if image is None or box is None:
        return None

    x1, y1, x2, y2 = box
    
    # Clamp to image bounds
    h_img, w_img = image.shape[:2]
    
    x1 = max(0, int(round(x1)))
    y1 = max(0, int(round(y1)))
    x2 = min(w_img, int(round(x2)))
    y2 = min(h_img, int(round(y2)))
    
    w = x2 - x1
    h = y2 - y1
    
    # Hard guards for crop sizes / Minimum box size: 4x4 pixels
    if w < 4 or h < 4:
        return None

    return image[y1:y2, x1:x2].copy()

def filter_noise_boxes(boxes: list, min_area: int = MIN_BOX_AREA) -> list:
    filtered = []
    for box in boxes:
        x1, y1, x2, y2 = box[:4]
        if (x2 - x1) * (y2 - y1) >= min_area:
            kept = [x1, y1, x2, y2]
            if len(box) > 4:
                kept.extend(box[4:])
            filtered.append(kept)
    return filtered
