class TTSBackend:
    """Abstract base for TTS backends."""

    name: str = ""

    def speak(self, text: str) -> None:
        raise NotImplementedError

    async def generate(self, text: str) -> str | None:
        """Generate audio for *text* and save to a temp file (no playback).

        Returns the path to the generated audio file, or ``None`` if the
        backend does not support file-based generation. Backends that do
        support it (e.g. EdgeTTS) should override this.
        """
        return None

    def stop(self) -> None:
        raise NotImplementedError

    def list_voices(self):
        return []

    def set_voice(self, voice_id):
        pass
