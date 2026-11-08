import numpy as np
import sounddevice as sd
from piper import PiperVoice

from receptionist.config import settings


class TextToSpeech:
    def __init__(self, voice_path: str = settings.tts_voice):
        self.voice = PiperVoice.load(voice_path)
        self.sample_rate = self.voice.config.sample_rate

    def synthesize(self, text: str) -> np.ndarray:
        chunks = [
            np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
            for chunk in self.voice.synthesize(text)
        ]
        if not chunks:
            return np.zeros(0, dtype=np.int16)
        return np.concatenate(chunks)

    def speak(self, text: str, wait: bool = True) -> None:
        audio = self.synthesize(text)
        if audio.size == 0:
            return
        sd.play(audio, self.sample_rate)
        if wait:
            sd.wait()

    def stop(self) -> None:
        """Cut playback immediately. Used later when the caller interrupts."""
        sd.stop()