import logging

from .base import TTSBackend
from .coeiroink_backend import COEIROINKBackend
from .edge_tts_backend import EdgeTTSBackend

logger = logging.getLogger(__name__)


class TTSManager:
    def __init__(self, backends):
        # register provided backends
        self.backends = {b.name: b for b in backends}
        self.last_audio_path: str | None = None

        # register COEIROINK only if not already provided
        if "coeiroink" not in self.backends:
            self.backends["coeiroink"] = COEIROINKBackend()
        # register Edge TTS only if not already provided
        if "edge_tts" not in self.backends:
            self.backends["edge_tts"] = EdgeTTSBackend()

        # default active backend
        self.active = next(iter(self.backends.values()))

    def set_backend(self, name: str):
        if name in self.backends:
            logger.debug("Switching backend: %s -> %s", self.active.name, name)
            self.active = self.backends[name]

    def speak(self, text: str):
        logger.debug("speak() active backend: %s", self.active.name)
        result = self.active.speak(text)
        self.last_audio_path = getattr(self.active, "last_audio_path", None)
        if result is None:
            return
        # Play returned audio data (COEIROINK etc.)
        try:
            import numpy as np
            import sounddevice as sd
            if isinstance(result, tuple) and len(result) == 2:
                wav, sr = result
            elif isinstance(result, np.ndarray):
                wav, sr = result, 44100
            else:
                return
            if isinstance(wav, np.ndarray) and wav.size > 0:
                audio = wav.astype(np.float32)
                if audio.max() > 1.0 or audio.min() < -1.0:
                    audio = audio / 32768.0
                sd.play(audio, samplerate=sr, blocking=False)
        except Exception as exc:
            logger.warning("Audio playback failed: %s", exc)

    def stop(self):
        if hasattr(self.active, "stop"):
            self.active.stop()

    def list_voices(self):
        all_voices = []
        # Put active backend first so UI selector matches
        active_name = self.active.name
        if active_name in self.backends:
            backend = self.backends[active_name]
            if hasattr(backend, "list_voices"):
                for voice_name, voice_id in backend.list_voices():
                    all_voices.append((voice_name, f"{active_name}|{voice_id}"))
        for name, backend in self.backends.items():
            if name == active_name:
                continue
            if hasattr(backend, "list_voices"):
                for voice_name, voice_id in backend.list_voices():
                    all_voices.append((voice_name, f"{name}|{voice_id}"))
        return all_voices

    def set_voice(self, voice_id):
        logger.debug("set_voice() received: %s", voice_id)
        if "|" in voice_id:
            backend_name, real_id = voice_id.split("|", 1)
            logger.debug("Parsed backend=%s, voice=%s", backend_name, real_id)
            self.set_backend(backend_name)
            voice_id = real_id
        logger.debug("Active backend now: %s", self.active.name)
        if hasattr(self.active, "set_voice"):
            self.active.set_voice(voice_id)
