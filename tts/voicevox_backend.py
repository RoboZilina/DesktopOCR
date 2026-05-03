import logging

from .base import TTSBackend

logger = logging.getLogger(__name__)


class VoiceVoxBackend(TTSBackend):
    name = "voicevox"

    def speak(self, text: str) -> None:
        logger.debug("VoiceVox speak: %s", text)

    def stop(self) -> None:
        pass

    def list_voices(self):
        return []
