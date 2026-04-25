"""Edge TTS backend — lightweight cloud-based Japanese speech synthesis."""
import asyncio
import io
import logging

logger = logging.getLogger(__name__)

VOICE_DEFAULT = "ja-JP-NanamiNeural"
VOICES = {
    "nanami": "ja-JP-NanamiNeural",
    "keita": "ja-JP-KeitaNeural",
    "aoi": "ja-JP-AoiNeural",
}


class EdgeTTS:
    """Cloud TTS via Microsoft Edge speech API (requires internet)."""

    def __init__(self, voice: str = VOICE_DEFAULT):
        self.voice = voice
        self._lock = asyncio.Lock()
        self._enabled = True
        try:
            import pygame
            pygame.mixer.init()
        except Exception as exc:
            logger.warning("pygame unavailable; Edge TTS audio playback will not work: %s", exc)

    async def speak(self, text: str) -> None:
        logger.info("EdgeTTS.speak() called: text=%s", text[:50])
        if not self._enabled or not text:
            logger.info("EdgeTTS.speak() skipped: enabled=%s text=%s", self._enabled, bool(text))
            return
        if self._lock.locked():
            logger.info("EdgeTTS.speak() skipped: lock is held")
            return  # skip if already speaking
        try:
            import edge_tts
            import pygame
        except Exception as exc:
            logger.error("EdgeTTS.speak() import failed: %s", exc, exc_info=True)
            return
        logger.info("EdgeTTS.speak() speaking voice=%s", self.voice)
        async with self._lock:
            try:
                audio_bytes = b""
                communicate = edge_tts.Communicate(text, self.voice)
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_bytes += chunk["data"]
                if audio_bytes:
                    logger.info("EdgeTTS.speak() got %d bytes, playing...", len(audio_bytes))
                    pygame.mixer.music.load(io.BytesIO(audio_bytes))
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        await asyncio.sleep(0.1)
                    logger.info("EdgeTTS.speak() playback complete")
                else:
                    logger.warning("EdgeTTS.speak() no audio received")
            except Exception as exc:
                logger.error("Edge TTS speak error: %s", exc, exc_info=True)

    async def stop(self) -> None:
        try:
            import pygame
            pygame.mixer.music.stop()
        except Exception:
            pass

    def set_voice(self, voice_key: str) -> None:
        voice = VOICES.get(voice_key)
        if voice:
            self.voice = voice
            logger.info("Edge TTS voice set to: %s", voice)
        else:
            logger.warning("Unknown Edge TTS voice key: %s", voice_key)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    async def dispose(self) -> None:
        await self.stop()
        try:
            import pygame
            pygame.mixer.quit()
        except Exception:
            pass
