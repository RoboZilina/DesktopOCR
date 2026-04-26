"""Google Cloud Vision OCR helper (Bring Your Own Key)."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class GoogleVisionOCR:
    """Minimal wrapper around Google Cloud Vision's TEXT_DETECTION API."""

    _VISION_URL = "https://vision.googleapis.com/v1/images:annotate"

    def __init__(self, api_key: str = "", enabled: bool = False) -> None:
        self.api_key = (api_key or "").strip()
        self._enabled = bool(enabled and self.api_key)
        self._client: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()
        self._invalid_key_logged = False

    def update_settings(self, *, api_key: str | None = None, enabled: bool | None = None) -> None:
        """Update BYOK configuration at runtime."""
        if api_key is not None:
            self.api_key = api_key.strip()
            self._invalid_key_logged = False
            if not self.api_key:
                self._enabled = False
        if enabled is not None:
            self._enabled = bool(enabled and self.api_key)

    def is_enabled(self) -> bool:
        return bool(self._enabled and self.api_key)

    async def close(self) -> None:
        if self._client and not self._client.closed:
            await self._client.close()
            self._client = None

    async def _get_client(self) -> aiohttp.ClientSession:
        if self._client is None or self._client.closed:
            timeout = aiohttp.ClientTimeout(total=3)
            self._client = aiohttp.ClientSession(timeout=timeout)
        return self._client

    async def ocr_image(self, image_bytes: bytes) -> str | None:
        """Send the given image bytes to Google Vision; return text or None."""
        if not self.is_enabled() or not image_bytes:
            return None

        if self._lock.locked():
            logger.debug("GoogleVisionOCR: skipping overlapping request (lock held)")
            return None

        async with self._lock:
            try:
                client = await self._get_client()
                payload = {
                    "requests": [
                        {
                            "image": {"content": base64.b64encode(image_bytes).decode("ascii")},
                            "features": [{"type": "TEXT_DETECTION"}],
                        }
                    ]
                }
                url = f"{self._VISION_URL}?key={self.api_key}"
                async with client.post(url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        text = self._extract_text(data)
                        return text.strip() if text else None

                    if response.status in (400, 401, 403):
                        if not self._invalid_key_logged:
                            logger.warning(
                                "Google Vision OCR auth failed (status %s). Verify your API key.",
                                response.status,
                            )
                            self._invalid_key_logged = True
                        return None

                    logger.warning(
                        "Google Vision OCR returned status %s — falling back to local engine",
                        response.status,
                    )
                    return None

            except asyncio.TimeoutError:
                logger.warning("Google Vision OCR request timed out; using local engine instead")
                return None
            except Exception as exc:  # noqa: BLE001 — network errors are expected
                logger.error("Google Vision OCR error: %s", exc)
                return None

    def _extract_text(self, payload: dict[str, Any]) -> str | None:
        responses = payload.get("responses") or []
        if not responses:
            return None

        first = responses[0]
        if "error" in first:
            logger.warning(
                "Google Vision OCR response error: %s",
                first.get("error", {}).get("message", "unknown"),
            )
            return None

        annotations = first.get("textAnnotations") or []
        if not annotations:
            return None

        description = annotations[0].get("description")
        if isinstance(description, str) and description.strip():
            return description

        return None
