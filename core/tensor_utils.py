import cv2
import numpy as np

# Shared resources for zero-churn tensor conversion
# Pre-allocate once, reuse every frame — never allocate inside the hot path
DET_BUFFER = np.zeros((1, 3, 960, 960), dtype=np.float32)
REC_BUFFER = np.zeros((1, 3, 48, 320), dtype=np.float32)

# Detection box padding (applied in detection-space BEFORE scaling to original coords)
PAD_LEFT = 20
PAD_RIGHT = 12
PAD_TOP = 12
PAD_BOTTOM = 12

MIN_BOX_AREA = 40 * 40


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


def pad_left(image: np.ndarray, px: int = 4) -> np.ndarray:
    if image is None or image.size == 0 or px <= 0:
        return image
    h, w = image.shape[:2]
    out = np.zeros((h, w + px, 3), dtype=np.uint8)
    out[:, px:] = image
    return out


def boost_contrast(image: np.ndarray, alpha: float = 1.08) -> np.ndarray:
    if image is None or image.size == 0:
        return image
    return cv2.convertScaleAbs(image, alpha=alpha, beta=0)


def preprocess_paddle_slice(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        return image
    trimmed = trim_empty_vertical(image)
    padded = pad_left(trimmed, px=4)
    return boost_contrast(padded, alpha=1.08)

def image_to_det_tensor(image: np.ndarray) -> np.ndarray:
    """
    canvasToFloat32Tensor equivalent for detection
    Resize to 960x960 (direct stretch, matching web Paddle path)
    """
    source = image
    target_h, target_w = 960, 960
    canvas = cv2.resize(source, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
    
    # Normalize: (pixel/255 - 0.5) / 0.5
    img_float = canvas.astype(np.float32)
    img_float = (img_float / 255.0 - 0.5) / 0.5
    
    # HWC to CHW
    img_chw = img_float.transpose(2, 0, 1)
    
    # Write into DET_BUFFER in-place
    DET_BUFFER[0] = img_chw
    
    # Fallback for internal shared buffers (Legacy Copy logic)
    return DET_BUFFER.copy()

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
    
    # Apply same padding from instructions.md
    x1 -= PAD_LEFT
    y1 -= PAD_TOP
    x2 += PAD_RIGHT
    y2 += PAD_BOTTOM
    
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
        x1, y1, x2, y2 = box
        if (x2 - x1) * (y2 - y1) >= min_area:
            filtered.append(box)
    return filtered
