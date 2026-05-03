"""MyMemory Translation API backend — no API key required.

Free, unlimited-ish for small VN text segments. Uses simple HTTP GET.
https://mymemory.translated.net/doc/spec.php
"""

import logging

import aiohttp

from core.translation.base import TranslationBackend

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.mymemory.translated.net/get"
_TIMEOUT = aiohttp.ClientTimeout(total=10)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


class MyMemoryBackend(TranslationBackend):
    """Translates via the free MyMemory web API — zero auth required."""

    name: str = "MyMemory"

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    def _get_session(self) -> aiohttp.ClientSession:
        """Return existing session or create a new one lazily."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=_TIMEOUT)
        return self._session

    async def translate(
        self,
        text: str,
        source: str = "ja",
        target: str = "en",
    ) -> str:
        """Translate text via MyMemory API.

        Returns translated string, or "" on any failure.
        """
        if not text or not text.strip():
            return ""

        params = {
            "q": text,
            "langpair": f"{source}|{target}",
        }

        try:
            session = self._get_session()
            async with session.get(
                _ENDPOINT,
                params=params,
                headers=_HEADERS,
            ) as resp:
                if resp.status != 200:
                    logger.warning(
                        "[MyMemory] HTTP %d from endpoint", resp.status
                    )
                    return ""

                data = await resp.json(content_type=None)
                response_data = data.get("responseData", {})
                result = (response_data.get("translatedText") or "").strip()
                if result:
                    logger.info(
                        "[MyMemory] Translated %d chars -> %r",
                        len(text), result[:60],
                    )
                    return result

                logger.warning(
                    "[MyMemory] Empty responseData: %r", str(data)[:200]
                )
                return ""

        except aiohttp.ClientError as exc:
            logger.warning("[MyMemory] Network error: %s", exc)
            return ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("[MyMemory] Unexpected error: %s", exc)
            return ""

    async def is_available(self) -> bool:
        """Return True if the MyMemory endpoint is reachable."""
        params = {"q": "test", "langpair": "ja|en"}
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
