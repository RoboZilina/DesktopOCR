import logging
import os
import re

import numpy as np
import pyopenjtalk
import sounddevice as sd

from .base import TTSBackend

logger = logging.getLogger(__name__)


class OpenJTalkBackend(TTSBackend):
    name = "openjtalk"

    def __init__(self):
        logger.info("OpenJTalkBackend initialized")
        self._rate = 1.0
        self._volume = 1.0

    def _clean_text(self, text: str) -> str:
        """Strip non-Japanese punctuation that confuses OpenJTalk."""
        # Keep hiragana, katakana, kanji, basic ASCII letters/numbers
        # Remove exclamation, question marks, special unicode punctuation
        cleaned = re.sub(r'[^\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF\u3400-\u4DBFa-zA-Z0-9\s]', '', text)
        # Collapse multiple spaces
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        logger.debug("Cleaned text: '%s'", cleaned[:50])
        return cleaned or text  # Fallback to original if everything stripped

    def list_voices(self):
        return [("OpenJTalk (JP)", "openjtalk_default")]

    def set_voice(self, voice_id):
        logger.debug("OpenJTalk voice set to: %s", voice_id)

    def set_rate(self, rate: float):
        self._rate = max(0.5, min(2.0, rate))
        logger.debug("OpenJTalk rate set to: %s", self._rate)

    def set_volume(self, volume: float):
        self._volume = max(0.0, min(1.0, volume))
        logger.debug("OpenJTalk volume set to: %s", self._volume)

    def speak(self, text: str):
        if not text or not text.strip():
            logger.info("OpenJTalk: no text to speak")
            return

        logger.debug("OpenJTalk raw input: %s...", text[:60])

        cleaned = self._clean_text(text)

        # Debug: show phoneme representation
        try:
            phonemes = pyopenjtalk.g2p(cleaned)
            logger.debug("g2p phonemes: %s...", phonemes[:80])
        except Exception as e:
            logger.warning("g2p failed: %s", e)

        # Synthesize
        try:
            wav, sr = pyopenjtalk.tts(cleaned)
        except Exception as e:
            logger.error("pyopenjtalk.tts() failed: %s", e)
            return

        # Apply volume
        wav = wav * self._volume

        # Apply rate (speed) by resampling playback rate
        play_sr = int(sr * (1.0 / self._rate))

        # Normalize int16 range to float32 [-1.0, 1.0] for sounddevice
        wav = np.asarray(wav, dtype=np.float32)
        if wav.max() > 1.0 or wav.min() < -1.0:
            wav = wav / 32768.0
        if wav.ndim == 1:
            wav = wav.reshape(-1, 1)

        # Debug save to WAV (only when DESKTOCR_TTS_DEBUG_WAV=1)
        if os.getenv("DESKTOCR_TTS_DEBUG_WAV", "0") == "1":
            try:
                from scipy.io import wavfile
                wavfile.write("last_tts.wav", play_sr, (wav * 32768).astype(np.int16))
                logger.info("Saved last_tts.wav for inspection")
            except Exception as e:
                logger.warning("WAV save failed (scipy not installed?): %s", e)

        # Play (non-blocking so UI stays responsive)
        try:
            sd.play(wav, samplerate=play_sr, blocking=False)
        except Exception as e:
            logger.error("sd.play() failed: %s", e)

    def stop(self):
        sd.stop()
