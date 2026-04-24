class TTSBackend:
    """Abstract base for TTS backends."""

    name: str = ""

    def speak(self, text: str) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def list_voices(self):
        return []

    def set_voice(self, voice_id):
        pass
