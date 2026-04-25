import requests
import numpy as np

from .base import TTSBackend


class COEIROINKBackend(TTSBackend):
    name = "coeiroink"

    def __init__(self, speaker_uuid="3c37646f-3881-5374-2a83-149267990abc", style_id="0"):
        self.base_url = "http://127.0.0.1:50032"
        self.speaker_uuid = speaker_uuid
        self.style_id = style_id

    def list_voices(self):
        try:
            response = requests.get(
                f"{self.base_url}/v1/speakers",
                timeout=5
            )
            response.raise_for_status()
            speakers = response.json()
            voices = []
            name_map = {
                "3c37646f-3881-5374-2a83-149267990abc": "Tsukuyomi-chan",
                "d41bcbd9-f4a9-4e10-b000-7a431568dd01": "Kanae",
                "d1143ac1-c486-4273-92ef-a30938d01b91": "Ayaka",
            }
            style_map = {
                "0": "Calm",
                "1": "Gentle",
                "2": "Energetic",
                "50": "Normal v2",
                "100": "Normal",
                "101": "Joy A",
                "102": "Happiness",
                "103": "Joy B",
            }
            for speaker in speakers:
                uuid = speaker.get("speakerUuid", "")
                name = name_map.get(uuid, speaker.get("speakerName", "Unknown"))
                styles = speaker.get("styles", [])
                for style in styles:
                    sid = str(style.get("styleId", "0"))
                    style_name = style_map.get(sid, style.get("styleName", sid))
                    voices.append((f"{name} ({style_name})", sid))
            return voices or [("Tsukuyomi-chan (Calm)", "0")]
        except Exception:
            return [("Tsukuyomi-chan (Calm)", "0")]

    def set_voice(self, voice_id):
        print(f"[COEIROINK] Voice style set to: {voice_id}")
        self.style_id = voice_id

    def speak(self, text):
        if not text or not text.strip():
            return None

        try:
            response = requests.post(
                f"{self.base_url}/v1/predict",
                json={
                    "speakerUuid": self.speaker_uuid,
                    "styleId": self.style_id,
                    "text": text,
                    "speedScale": 1.0,
                    "volumeScale": 1.0,
                    "pitchScale": 0.0,
                    "intonationScale": 1.0,
                    "prePhonemeLength": 0.1,
                    "postPhonemeLength": 0.1,
                },
                timeout=60,
            )

            if response.content == b"Internal Server Error":
                print("[COEIROINK] Internal Server Error (invalid speaker/style?)")
                return None

            response.raise_for_status()

            wav_bytes = response.content
            pcm, sr = self._wav_bytes_to_pcm(wav_bytes)
            return pcm, sr

        except requests.exceptions.ConnectionError:
            print("[COEIROINK] Engine not running")
            return None
        except requests.exceptions.RequestException as e:
            print(f"[COEIROINK] Error: {e}")
            return None

    def _wav_bytes_to_pcm(self, wav_bytes):
        import struct
        # Parse WAV: extract sample rate and PCM data
        if wav_bytes[:4] != b"RIFF" or wav_bytes[8:12] != b"WAVE":
            return None, 44100

        sr = 44100
        pos = 12
        while pos < len(wav_bytes) - 8:
            chunk_id = wav_bytes[pos:pos + 4]
            chunk_size = struct.unpack("<I", wav_bytes[pos + 4:pos + 8])[0]
            if chunk_id == b"fmt ":
                if chunk_size >= 16:
                    sr = struct.unpack("<I", wav_bytes[pos + 12:pos + 16])[0]
                pos += 8 + chunk_size
            elif chunk_id == b"data":
                data = wav_bytes[pos + 8:pos + 8 + chunk_size]
                return np.frombuffer(data, dtype=np.int16), sr
            else:
                pos += 8 + chunk_size

        return None, sr
