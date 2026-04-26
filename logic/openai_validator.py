import asyncio
import aiohttp
import logging

logger = logging.getLogger(__name__)

class OpenAIValidator:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self._model = model
        self._enabled = True
        self._lock = asyncio.Lock()
        self._client: aiohttp.ClientSession | None = None
        self._cost_estimate_chars = 0

    async def _get_client(self) -> aiohttp.ClientSession:
        if self._client is None or self._client.closed:
            self._client = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
            )
        return self._client

    async def validate_and_fix(self, text: str) -> str:
        if not self._enabled or not text or not self.api_key:
            return text

        if self._lock.locked():
            return text

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

                async with client.post("https://api.openai.com/v1/chat/completions", json=payload, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        fixed_text = data["choices"][0]["message"]["content"].strip()
                        self._cost_estimate_chars += len(text)
                        return fixed_text
                    else:
                        logger.warning("OpenAI API returned status %d", response.status)
                        return text

            except Exception as e:
                logger.error("OpenAI validator error: %s", e)
                return text

    async def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    @property
    def cost_estimate_chars(self) -> int:
        return self._cost_estimate_chars

    async def dispose(self) -> None:
        if self._client and not self._client.closed:
            await self._client.close()
