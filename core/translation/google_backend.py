"""Google Translate free web endpoint backend — no API key required.

Uses the same endpoint as the translate.googleapis.com single-query URL
that the Google Translate web app itself uses for quick lookups.
"""

import logging

import aiohttp

from core.translation.base import TranslationBackend

logger = logging.getLogger(__name__)

_ENDPOINT = "https://translate.googleapis.com/translate_a/single"
_TIMEOUT = aiohttp.ClientTimeout(total=10)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


class GoogleTranslateBackend(TranslationBackend):
    """Translates via Google's free single-query web endpoint."""

    name: str = "Google"

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=_TIMEOUT)
        return self._session

    async def translate(
        self,
        text: str,
        source: str = "ja",
        target: str = "en",
    ) -> str:
        """Translate text via Google Translate free endpoint.

        Returns translated string, or "" on any failure.
        """
        if not text or not text.strip():
            return ""

        params = {
            "client": "gtx",
            "sl": source,
            "tl": target,
            "dt": "t",
            "q": text,
        }

        try:
            session = self._get_session()
            async with session.get(
                _ENDPOINT,
                params=params,
                headers=_HEADERS,
            ) as resp:
                if resp.status != 200:
                    logger.warning("[Google] HTTP %d from endpoint", resp.status)
                    return ""

                data = await resp.json(content_type=None)
                # Response: [ [ ["translated", "original", ...], ... ], ... ]
                if not data or not isinstance(data, list) or not data[0]:
                    logger.warning("[Google] Unexpected response structure: %r", str(data)[:100])
                    return ""

                parts = [
                    segment[0]
                    for segment in data[0]
                    if isinstance(segment, list) and segment and segment[0]
                ]
                result = "".join(parts).strip()
                logger.info("[Google] Translated %d chars -> %r", len(text), result[:60])
                return result

        except aiohttp.ClientError as exc:
            logger.warning("[Google] Network error: %s", exc)
            return ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Google] Unexpected error: %s", exc)
            return ""

    async def is_available(self) -> bool:
        """Return True if the Google Translate endpoint is reachable."""
        params = {"client": "gtx", "sl": "ja", "tl": "en", "dt": "t", "q": "test"}
        try:
            session = self._get_session()
            async with session.get(
                _ENDPOINT,
                params=params,
                headers=_HEADERS,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                return resp.status == 200
        except Exception:  # noqa: BLE001
            return False

    async def dispose(self) -> None:
        """Close the underlying aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
