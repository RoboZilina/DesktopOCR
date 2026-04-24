from .base import TTSBackend


class TTSManager:
    def __init__(self, backends):
        self.backends = {b.name: b for b in backends}
        self.active = next(iter(self.backends.values()))

    def speak(self, text: str):
        self.active.speak(text)

    def stop(self):
        self.active.stop()

    def list_voices(self):
        return self.active.list_voices()

    def set_voice(self, voice_id):
        self.active.set_voice(voice_id)
