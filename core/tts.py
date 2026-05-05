"""Edge TTS backend — lightweight cloud-based Japanese speech synthesis."""
import asyncio
import io
import logging
import os
import tempfile

logger = logging.getLogger(__name__)

VOICE_DEFAULT = "ja-JP-NanamiNeural"
VOICES = {
    "nanami": "ja-JP-NanamiNeural",
    "keita": "ja-JP-KeitaNeural",
}


class EdgeTTS:
    """Cloud TTS via Microsoft Edge speech API (requires internet)."""

    def __init__(self, voice: str = VOICE_DEFAULT):
        self.voice = voice
        self._lock = asyncio.Lock()
        self._enabled = True
        self.last_audio_path: str | None = None
        self._last_audio_path: str | None = None
        self._mixer_available = False
        try:
            import pygame
            pygame.mixer.init()
            self._mixer_available = True
        except Exception as exc:
            logger.warning("pygame unavailable; Edge TTS audio playback will not work: %s", exc)

    async def speak(self, text: str, play_audio: bool = True) -> None:
        """Generate TTS audio, save to temp file, and optionally play it back.

        Args:
            text: The text to synthesize.
            play_audio: If ``True`` (default), also play audio via pygame.
                Set to ``False`` to silently generate and save only
                (e.g. for Anki card audio attachment).
        """
        logger.info("EdgeTTS.speak() called: text=%s play_audio=%r", text[:50], play_audio)
        if not self._enabled or not text:
            logger.info("EdgeTTS.speak() skipped: enabled=%s text=%s", self._enabled, bool(text))
            return
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
                    logger.info("EdgeTTS.speak() got %d bytes", len(audio_bytes))
                    # Save audio to temp file (always — for Anki attachment).
                    # NOTE: Do NOT clean up previous temp files here — the caller
                    # (main.py) may call generate() multiple times (selection +
                    # context audio), and deleting the previous file would destroy
                    # the first path before the card builder can read it.
                    try:
                        fd, path = tempfile.mkstemp(suffix=".mp3", prefix="desktopocr_anki_")
                        with os.fdopen(fd, "wb") as f:
                            f.write(audio_bytes)
                        self.last_audio_path = path
                        self._last_audio_path = path
                        logger.info("EdgeTTS.speak() saved audio to %s", path)
                    except Exception as exc:
                        logger.warning("EdgeTTS.speak() failed to save audio: %s", exc)
                    # Play audio via pygame (only when requested)
                    if play_audio and self._mixer_available:
                        try:
                            pygame.mixer.music.load(io.BytesIO(audio_bytes))
                            pygame.mixer.music.play()
                            while pygame.mixer.music.get_busy():
                                await asyncio.sleep(0.1)
                            logger.info("EdgeTTS.speak() playback complete")
                        except Exception as exc:
                            logger.warning("EdgeTTS.speak() playback failed: %s", exc)
                    elif play_audio and not self._mixer_available:
                        logger.warning("EdgeTTS.speak() playback requested but pygame mixer is not available")
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
            logger.warning("Unknown Edge TTS voice key '%s', falling back to %s", voice_key, VOICE_DEFAULT)
            self.voice = VOICE_DEFAULT

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    async def dispose(self) -> None:
        await self.stop()
        try:
            import pygame
            pygame.mixer.quit()
        except Exception:
            pass
