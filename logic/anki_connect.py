"""AnkiConnect HTTP client — communicates with the AnkiConnect add-on."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# aiohttp is the preferred transport; fall back to urllib if unavailable.
try:
    import aiohttp

    _HAS_AIOHTTP = True
except ImportError:  # pragma: no cover
    _HAS_AIOHTTP = False


class AnkiConnect:
    """Async client for the AnkiConnect HTTP API.

    All public methods catch exceptions, log them at WARNING with an ``[Anki]``
    prefix, and never raise.  This makes it safe to call from UI event handlers
    without try/except wrappers.
    """

    def __init__(self, host: str = "localhost", port: int = 8765) -> None:
        self._base_url = f"http://{host}:{port}"
        self._session: Any | None = None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        if _HAS_AIOHTTP:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession()
            return self._session
        return None  # type: ignore[return-value]

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Low-level request
    # ------------------------------------------------------------------

    async def _request(self, action: str, params: dict | None = None, *,
                       timeout: float = 10.0) -> dict[str, Any] | None:
        """POST a JSON-RPC request to AnkiConnect and return the response dict.

        Returns ``None`` on any failure (connection error, timeout, non-JSON
        response, or an error field in the response).
        """
        payload = {
            "action": action,
            "version": 6,
            "params": params or {},
        }
        body = json.dumps(payload, ensure_ascii=False)

        if _HAS_AIOHTTP:
            return await self._request_aiohttp(body, timeout)
        return await self._request_urllib(body, timeout)

    async def _request_aiohttp(self, body: str, timeout: float) -> dict[str, Any] | None:
        session = await self._get_session()
        try:
            async with session.post(
                self._base_url,
                data=body,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    logger.warning("[Anki] HTTP %d from %s", resp.status, self._base_url)
                    return None
                data = await resp.json()
                if "error" in data and data["error"] is not None:
                    logger.warning("[Anki] Error in '%s': %s", json.loads(body)["action"], data["error"])
                    return None
                return data
        except (asyncio.TimeoutError, aiohttp.ClientError, json.JSONDecodeError) as exc:
            logger.warning("[Anki] Request failed: %s", exc)
            return None

    async def _request_urllib(self, body: str, timeout: float) -> dict[str, Any] | None:
        """Fallback using urllib.request wrapped in a thread-pool executor."""
        import urllib.request  # noqa: PLC0415

        loop = asyncio.get_running_loop()

        def _sync_post() -> dict[str, Any] | None:
            req = urllib.request.Request(
                self._base_url,
                data=body.encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if "error" in data and data["error"] is not None:
                        logger.warning(
                            "[Anki] Error in '%s': %s",
                            json.loads(body)["action"],
                            data["error"],
                        )
                        return None
                    return data
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("[Anki] Request failed: %s", exc)
                return None

        return await loop.run_in_executor(None, _sync_post)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def is_available(self) -> bool:
        """Check whether AnkiConnect is reachable.

        Returns ``True`` if the ``version`` action returns a numeric result.
        """
        data = await self._request("version", timeout=2.0)
        if data is None:
            return False
        result = data.get("result")
        return isinstance(result, (int, float))

    async def ensure_deck(self, deck_name: str) -> bool:
        """Create the deck *deck_name* if it does not already exist.

        Returns ``True`` on success (deck exists or was created).
        """
        data = await self._request("createDeck", {"deck": deck_name})
        return data is not None

    async def ensure_note_type(self) -> bool:
        """Ensure the ``DesktopOCR`` note type (model) exists.

        Checks via ``modelNames`` and creates it via ``createModel`` if missing.
        Returns ``True`` if the model exists after the call.
        """
        # Check if model already exists
        data = await self._request("modelNames")
        if data is None:
            return False
        models: list[str] = data.get("result") or []
        if "DesktopOCR" in models:
            return True

        # Create the model
        fields = [
            "Front",
            "Back",
            "TargetText",
            "TargetTranslation",
            "ContextText",
            "ContextTranslation",
            "Screenshot",
        ]
        css = (
            ".card { font-family: sans-serif; font-size: 20px; }"
            " .target { font-size: 28px; font-weight: bold; }"
            " .context { font-size: 16px; color: #666; }"
            " .translation { color: #2a6; margin-top: 8px; }"
            " .context-translation { color: #888; font-size: 14px; }"
        )
        templates = [
            {
                "Name": "DesktopOCR Card",
                "Front": "{{Front}}",
                "Back": "{{FrontSide}}<hr>{{Back}}",
            },
        ]
        data = await self._request("createModel", {
            "modelName": "DesktopOCR",
            "inOrderFields": fields,
            "css": css,
            "cardTemplates": templates,
        })
        if data is not None:
            logger.info("[Anki] Created note type 'DesktopOCR'")
            return True
        logger.warning("[Anki] Failed to create note type 'DesktopOCR'")
        return False

    async def add_note(
        self,
        deck_name: str,
        fields: dict[str, str],
        tags: list[str] | None = None,
        *,
        audio: dict | None = None,
        picture: dict | None = None,
    ) -> int | None:
        """Add a new note to *deck_name*.

        Args:
            deck_name: Target deck name.
            fields: Dict mapping field names to their HTML/text content.
            tags: Optional list of tag strings.
            audio: Optional audio dict with keys ``data``, ``filename``, ``fields``.
            picture: Optional picture dict with keys ``data``, ``filename``, ``fields``.

        Returns:
            The new note ID (int) on success, or ``None`` on failure.
        """
        note: dict[str, Any] = {
            "deckName": deck_name,
            "modelName": "DesktopOCR",
            "fields": fields,
            "tags": tags or [],
            "options": {"allowDuplicate": False},
        }
        if audio is not None:
            note["audio"] = [audio]
        if picture is not None:
            note["picture"] = [picture]

        data = await self._request("addNote", {"note": note})
        if data is None:
            return None
        result = data.get("result")
        if isinstance(result, int):
            return result
        # AnkiConnect may return a float for note IDs on some versions
        if isinstance(result, float):
            return int(result)
        return None
