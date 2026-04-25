"""Edge TTS backend wrapper — cloud-based, zero local size, requires internet."""
import asyncio
import logging

from .base import TTSBackend
from core.tts import EdgeTTS, VOICES

logger = logging.getLogger(__name__)


class EdgeTTSBackend(TTSBackend):
    """Microsoft Edge TTS — cloud, lightweight, Japanese male/female voices."""

    name = "edge_tts"

    def __init__(self):
        self._tts = EdgeTTS()

    def speak(self, text: str):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.info("EdgeTTS scheduling speak() task")
                asyncio.create_task(self._tts.speak(text))
            else:
                logger.info("EdgeTTS running speak() synchronously")
                loop.run_until_complete(self._tts.speak(text))
        except Exception as exc:
            logger.error("EdgeTTS speak scheduling failed: %s", exc, exc_info=True)

    def stop(self):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._tts.stop())
            else:
                loop.run_until_complete(self._tts.stop())
        except Exception:
            pass

    def list_voices(self):
        return [
            ("Edge Nanami ☁️", "nanami"),
            ("Edge Keita ☁️", "keita"),
            ("Edge Aoi ☁️", "aoi"),
        ]

    def set_voice(self, voice_id):
        self._tts.set_voice(voice_id)
