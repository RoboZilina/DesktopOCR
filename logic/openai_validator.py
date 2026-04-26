import asyncio
import aiohttp
import logging

logger = logging.getLogger(__name__)

class OpenAIValidator:
    _TIMEOUT = aiohttp.ClientTimeout(total=4)

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key.strip()
        self._model = model
        self._enabled = True
        self._lock = asyncio.Lock()
        self._client: aiohttp.ClientSession | None = None
        self._cost_estimate_chars = 0

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
            self._model = model
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
                    "Content-Type": "application/json"
                }
            )
        return self._client

    async def validate_and_fix(self, text: str) -> dict | None:
        if not self._enabled or not text or not self.api_key:
            return None

        if self._lock.locked():
            return None

        async with self._lock:
            try:
                client = await self._get_client()
                
                system_prompt = (
                    "You are a Japanese OCR post-processor for visual novels. "
                    "Fix OCR errors in the input text. Rules:\n"
                    "- Correct obvious character substitutions (ﾛ→口, 0→O in names)\n"
                    "- Fix broken kanji that were split by OCR noise\n"
                    "- Remove stray punctuation that does not belong\n"
                    "- Preserve the original meaning exactly — do not translate\n"
                    "- Preserve all Japanese characters, punctuation, and style\n"
                    "- If the text looks correct, return it unchanged\n"
                    "- Return ONLY the fixed text, no explanation, no quotes"
                )

                payload = {
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": text}
                    ],
                    "max_tokens": 200,
                    "temperature": 0
                }

                async with client.post(
                    "https://api.openai.com/v1/chat/completions",
                    json=payload,
                    timeout=self._TIMEOUT,
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        fixed_text = data["choices"][0]["message"]["content"].strip()
                        self._cost_estimate_chars += len(text)
                        return {"text": fixed_text, "source": "openai"}

                    logger.warning("OpenAI API returned status %d", response.status)
                    return None

            except Exception as e:
                logger.error("OpenAI validator error: %s", e)
                return None

    async def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    @property
    def cost_estimate_chars(self) -> int:
        return self._cost_estimate_chars

    async def dispose(self) -> None:
        if self._client and not self._client.closed:
            try:
                await self._client.close()
            except Exception:  # noqa: BLE001
                pass
        self._client = None
