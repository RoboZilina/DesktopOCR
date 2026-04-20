import asyncio
import logging
import numpy as np

logger = logging.getLogger(__name__)


def _resolve_enum_value(enum_obj, names: list[str]):
    for name in names:
        if hasattr(enum_obj, name):
            return getattr(enum_obj, name)
    raise AttributeError(f"None of {names} found on enum {enum_obj}")

def check_japanese_available() -> bool:
    try:
        # winsdk 0.10.0
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.globalization import Language
        
        return OcrEngine.is_language_supported(Language("ja"))
    except Exception as e:
        logger.warning(f"Windows OCR Japanese language check failed: {e}")
        return False

class WindowsOCR:
    """
    WinRT Windows.Media.Ocr fallback engine.
    NOTE: detect() is NOT implemented — Windows OCR reads the full image
    at once, it has no separate detection step.
    """
    
    def __init__(self):
        self.available = check_japanese_available()
        self._engine = None
        if not self.available:
            logger.warning("Windows OCR fallback initialized but Japanese is not available.")

    async def load(self) -> 'WindowsOCR':
        if not self.available:
            logger.warning("Cannot load Windows OCR: Japanese not available.")
            return self
            
        if self._engine is not None:
            return self

        try:
            # winsdk 0.10.0
            from winsdk.windows.media.ocr import OcrEngine
            from winsdk.windows.globalization import Language
            
            loop = asyncio.get_running_loop()
            
            self._engine = await loop.run_in_executor(
                None, lambda: OcrEngine.try_create_from_language(Language("ja"))
            )
            
            if self._engine is None:
                self.available = False
                logger.warning("Windows OCR engine could not be created for Japanese.")
                
        except Exception as e:
            self.available = False
            logger.error(f"Failed to initialize Windows OCR: {e}")
            
        return self

    async def recognize(self, image: np.ndarray) -> dict:
        if not self.available or self._engine is None:
            return {
                "text": "",
                "confidence": 0.0,
                "meta": {
                    "engine": "windows_ocr",
                    "warning": "windows_ocr_unavailable",
                },
            }

        try:
            # winsdk 0.10.0
            from winsdk.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode
            from winsdk.windows.storage.streams import DataWriter
            
            h, w = image.shape[:2]

            alpha = np.full((h, w, 1), 255, dtype=image.dtype)
            bgra = np.concatenate((image, alpha), axis=2).copy()

            pixel_format = _resolve_enum_value(
                BitmapPixelFormat,
                ["B_G_R_A8", "BGRA8"],
            )
            alpha_mode = _resolve_enum_value(
                BitmapAlphaMode,
                ["IGNORE", "PREMULTIPLIED", "STRAIGHT"],
            )

            bitmap = SoftwareBitmap(pixel_format, w, h, alpha_mode)
            writer = DataWriter()
            writer.write_bytes(bgra.tobytes())
            buffer = writer.detach_buffer()
            bitmap.copy_from_buffer(buffer)
            
            op = self._engine.recognize_async(bitmap)
            if hasattr(op, "__await__"):
                result = await op
            elif hasattr(op, "get_results"):
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, op.get_results)
            elif hasattr(op, "get"):
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, op.get)
            else:
                raise RuntimeError("Unsupported Windows OCR async operation type")
            
            # Extract result.text from OcrResult
            text = str(getattr(result, "text", "") or "")
            return {
                "text": text,
                "confidence": 0.0,
                "meta": {
                    "engine": "windows_ocr",
                    "ocr_chars": len(text),
                    "warning": "windows_ocr_confidence_unavailable",
                },
            }
            
        except Exception as e:
            logger.error(f"Windows OCR recognition error: {e}")
            return {
                "text": "",
                "confidence": 0.0,
                "meta": {
                    "engine": "windows_ocr",
                    "warning": f"windows_ocr_error: {e}",
                },
            }

    async def dispose(self):
        self._engine = None
        self.available = False
