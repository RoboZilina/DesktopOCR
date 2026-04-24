from .base import TTSBackend


class VoiceVoxBackend(TTSBackend):
    name = "voicevox"

    def speak(self, text: str) -> None:
        print("[TTS] VoiceVox speak:", text)

    def stop(self) -> None:
        pass

    def list_voices(self):
        return []
