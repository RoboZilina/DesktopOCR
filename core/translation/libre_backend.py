"""LibreTranslate local instance backend.

Requires LibreTranslate running locally:
  pip install libretranslate && libretranslate
  -- or --
  docker run -p 5000:5000 libretranslate/libretranslate

Japanese model downloads ~1GB on first run, then works fully offline.
"""

import logging

import aiohttp

from core.translation.base import TranslationBackend

logger = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=10)
_AVAIL_TIMEOUT = aiohttp.ClientTimeout(total=2)


class LibreTranslateBackend(TranslationBackend):
    """Translates via a local LibreTranslate instance."""

    name: str = "LibreTranslate"

    def __init__(self, base_url: str = "http://localhost:5000") -> None:
        self._base_url = base_url.rstrip("/")
        self._translate_url = f"{self._base_url}/translate"
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
        """Translate text via LibreTranslate.

        Returns translated string, or "" on any failure.
        """
        if not text or not text.strip():
            return ""

        payload = {
            "q": text,
            "source": source,
            "target": target,
            "format": "text",
        }

        try:
            session = self._get_session()
            async with session.post(
                self._translate_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status != 200:
                    logger.warning(
                        "[LibreTranslate] HTTP %d from %s",
                        resp.status,
                        self._translate_url,
                    )
                    return ""

                data = await resp.json(content_type=None)
                result = data.get("translatedText", "").strip()
                logger.info(
                    "[LibreTranslate] Translated %d chars → %r",
                    len(text),
                    result[:60],
                )
                return result

        except aiohttp.ClientError as exc:
            logger.warning("[LibreTranslate] Network error: %s", exc)
            return ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("[LibreTranslate] Unexpected error: %s", exc)
            return ""

    async def is_available(self) -> bool:
        """Return True if the LibreTranslate root endpoint responds with HTTP 200."""
        try:
            session = self._get_session()
            async with session.get(
                self._base_url + "/",
                timeout=_AVAIL_TIMEOUT,
            ) as resp:
                return resp.status == 200
        except Exception:  # noqa: BLE001
            return False

    async def dispose(self) -> None:
        """Close the underlying aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
