"""TranslationManager — tries backends in order, returns first success.

Design principles:
- Never raises — all exceptions are caught per-backend
- Lock prevents concurrent translations from piling up
- last_used_backend tracks which backend delivered the result
"""

import asyncio
import logging

from core.translation.base import TranslationBackend

logger = logging.getLogger(__name__)


class TranslationManager:
    """Tries a list of TranslationBackend instances in order.

    Returns the first non-empty result. If all backends fail, returns "".
    Uses an asyncio.Lock to prevent concurrent in-flight translations —
    if a translation is already running, new calls are skipped (return "").
    """

    def __init__(self, backends: list[TranslationBackend]) -> None:
        self._backends = backends
        self._last_used: str | None = None
        self._lock = asyncio.Lock()

    async def translate(self, text: str) -> str:
        """Translate text, returning "" on failure or empty input.

        Skips silently if a translation is already in progress.
        """
        if not text or not text.strip():
            return ""

        # Non-blocking lock check — skip if busy
        if self._lock.locked():
            logger.debug("[TranslationManager] Busy — skipping concurrent request")
            return ""

        async with self._lock:
            for backend in self._backends:
                try:
                    result = await backend.translate(text)
                    if result and result.strip():
                        self._last_used = backend.name
                        logger.info(
                            "[TranslationManager] Success via %s: %r",
                            backend.name,
                            result[:60],
                        )
                        return result
                    else:
                        logger.debug(
                            "[TranslationManager] Backend %s returned empty",
                            backend.name,
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[TranslationManager] Backend %s raised: %s",
                        backend.name,
                        exc,
                    )

            logger.warning("[TranslationManager] All backends failed for input: %r", text[:40])
            return ""

    async def check_availability(self) -> dict[str, bool]:
        """Check all backends concurrently.

        Returns {backend_name: is_available} dict.
        """
        async def _check(backend: TranslationBackend) -> tuple[str, bool]:
            try:
                available = await backend.is_available()
            except Exception:  # noqa: BLE001
                available = False
            return backend.name, available

        results = await asyncio.gather(*(_check(b) for b in self._backends))
        availability = dict(results)

        summary = ", ".join(
            f"{name}={'True' if ok else 'False'}"
            for name, ok in availability.items()
        )
        logger.info("[TranslationManager] Backend availability: %s", summary)
        return availability

    @property
    def last_used_backend(self) -> str | None:
        """Name of the backend that delivered the most recent successful translation."""
        return self._last_used

    async def dispose(self) -> None:
        """Dispose all backend sessions."""
        for backend in self._backends:
            if hasattr(backend, "dispose"):
                try:
                    await backend.dispose()
                except Exception:  # noqa: BLE001
                    pass
