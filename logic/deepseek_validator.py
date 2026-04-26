"""Budget-friendly DeepSeek validator backend."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

import aiohttp

logger = logging.getLogger(__name__)


class DeepSeekValidator:
    """Minimal wrapper around DeepSeek's OpenAI-compatible chat completions API."""

    _API_URL = "https://api.deepseek.com/v1/chat/completions"
    _TIMEOUT = aiohttp.ClientTimeout(total=4)

    def __init__(
        self,
        api_key: str = "",
        model: str = "deepseek-chat",
        enabled: bool = False,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self._model = model or "deepseek-chat"
        self._enabled = bool(enabled and self.api_key)
        self._lock = asyncio.Lock()
        self._client: aiohttp.ClientSession | None = None

    def update_settings(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        if api_key is not None:
            self.api_key = api_key.strip()
            self._reset_client()
        if model is not None:
            self._model = model.strip() or self._model
        if enabled is not None:
            self._enabled = bool(enabled)
        if not self.api_key:
            self._enabled = False

    def _reset_client(self) -> None:
        if self._client and not self._client.closed:
            old_client = self._client

            async def _close_old():
                try:
                    await old_client.close()
                except Exception:  # noqa: BLE001
                    pass

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_close_old())
            except RuntimeError:
                pass
        self._client = None

    async def _get_client(self) -> aiohttp.ClientSession:
        if self._client is None or self._client.closed:
            self._client = aiohttp.ClientSession(
                timeout=self._TIMEOUT,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
            )
        return self._client

    async def validate_and_fix(self, text: str) -> Dict[str, Any] | None:
        if not self._enabled or not self.api_key or not text:
            return None

        if self._lock.locked():
            logger.debug("DeepSeekValidator skipping request because lock is held")
            return None

        async with self._lock:
            try:
                client = await self._get_client()
                payload = {
                    "model": self._model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a Japanese OCR post-processor for visual novels. "
                                "Fix OCR glitches while preserving meaning and Japanese text."
                            ),
                        },
                        {"role": "user", "content": text},
                    ],
                    "temperature": 0,
                    "max_tokens": 200,
                }

                async with client.post(
                    self._API_URL,
                    json=payload,
                    timeout=self._TIMEOUT,
                ) as response:
                    if response.status != 200:
                        logger.warning(
                            "DeepSeek validator returned HTTP %s", response.status
                        )
                        return None

                    data = await response.json()
                    choices = data.get("choices") or []
                    if not choices:
                        logger.warning("DeepSeek validator response missing choices: %s", data)
                        return None

                    content = (
                        choices[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )
                    if not content:
                        return None

                    return {"text": content, "source": "deepseek"}

            except asyncio.TimeoutError:
                logger.warning("DeepSeek validator request timed out")
                return None
            except Exception as exc:  # noqa: BLE001
                logger.error("DeepSeek validator error: %s", exc)
                return None

    async def is_available(self) -> bool:
        return bool(self._enabled and self.api_key)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled and self.api_key)

    async def dispose(self) -> None:
        if self._client and not self._client.closed:
            try:
                await self._client.close()
            except Exception:  # noqa: BLE001
                pass
        self._client = None
