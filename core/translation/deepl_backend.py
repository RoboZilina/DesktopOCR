"""DeepL free web endpoint backend — no API key required.

Uses the same JSON-RPC endpoint as the DeepL browser extension.
Rate limits are generous for personal/VN use.
"""

import logging
import random

import aiohttp

from core.translation.base import TranslationBackend

logger = logging.getLogger(__name__)

_ENDPOINT = "https://www2.deepl.com/jsonrpc"
_TIMEOUT = aiohttp.ClientTimeout(total=10)

# Headers that mimic the DeepL web app — bare Content-Type alone triggers 429.
_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.deepl.com",
    "Referer": "https://www.deepl.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


class DeepLBackend(TranslationBackend):
    """Translates via DeepL's free web endpoint — zero auth required."""

    name: str = "DeepL"

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
        """Translate text using DeepL web endpoint.

        Returns translated string, or "" on any failure.
        """
        if not text or not text.strip():
            return ""

        payload = {
            "jsonrpc": "2.0",
            "method": "LMT_handle_texts",
            "id": random.randint(1000, 9999),
            "params": {
                "texts": [{"text": text, "requestedParagraphs": []}],
                "lang": {
                    "source_lang_user_selected": source.upper(),
                    "target_lang": target.upper(),
                },
            },
        }

        try:
            session = self._get_session()
            async with session.post(
                _ENDPOINT,
                json=payload,
                headers=_HEADERS,
            ) as resp:
                if resp.status != 200:
                    logger.warning(
                        "[DeepL] HTTP %d from endpoint", resp.status
                    )
                    return ""

                data = await resp.json(content_type=None)

                # Modern format: result.texts[].chunks[].sentences[]
                result_obj = data.get("result", {})
                texts_list = result_obj.get("texts", [])
                if texts_list:
                    parts = []
                    for text_entry in texts_list:
                        for chunk in text_entry.get("chunks", []):
                            for sentence in chunk.get("sentences", []):
                                s = sentence.get("text", "")
                                if s:
                                    parts.append(s)
                    if parts:
                        result = " ".join(parts).strip()
                        logger.info(
                            "[DeepL] Translated %d chars -> %r",
                            len(text), result[:60],
                        )
                        return result

                # Legacy format: result.translations[].beams[].sentences[]
                translations = result_obj.get("translations", [])
                if not translations:
                    logger.warning("[DeepL] Unrecognised response structure: %r", str(data)[:200])
                    return ""
                beams = translations[0].get("beams", [])
                if not beams:
                    logger.warning("[DeepL] No beams in first translation")
                    return ""
                sentences = beams[0].get("sentences", [])
                result = " ".join(s.get("text", "") for s in sentences).strip()
                logger.info(
                    "[DeepL] Translated (legacy) %d chars -> %r",
                    len(text), result[:60],
                )
                return result

        except aiohttp.ClientError as exc:
            logger.warning("[DeepL] Network error: %s", exc)
            return ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("[DeepL] Unexpected error: %s", exc)
            return ""

    async def is_available(self) -> bool:
        """Return True if the DeepL endpoint responds with HTTP 200."""
        # Send a minimal valid request — empty text returns an error body
        # but still HTTP 200, which is enough to confirm reachability.
        payload = {
            "jsonrpc": "2.0",
            "method": "LMT_handle_texts",
            "id": random.randint(1000, 9999),
            "params": {
                "texts": [{"text": "test", "requestedParagraphs": []}],
                "lang": {
                    "source_lang_user_selected": "JA",
                    "target_lang": "EN",
                },
            },
        }
        try:
            session = self._get_session()
            async with session.post(
                _ENDPOINT,
                json=payload,
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
