import re
import time

import numpy as np
import sounddevice as sd
from piper import PiperVoice

from receptionist.config import settings

DIGIT_WORDS = {
    "0": "oh", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}

# Six or more characters of digits/spaces: phone numbers, not times or years
LONG_NUMBER = re.compile(r"\d[\d ]{4,}\d")


def _chunk(digits: str) -> list[str]:
    """Split an unspaced number the way UK numbers are read: 5, then 3s."""
    if len(digits) <= 6:
        return [digits]
    return [digits[:5]] + [digits[i : i + 3] for i in range(5, len(digits), 3)]


def speakable(text: str) -> str:
    """Rewrite text so TTS reads phone numbers digit by digit."""

    def spell_out(match: re.Match) -> str:
        groups = []
        for part in match.group().split():
            groups.extend(_chunk(part))
        return ", ".join(" ".join(DIGIT_WORDS[d] for d in group) for group in groups)

    return LONG_NUMBER.sub(spell_out, text)


class TextToSpeech:
    def __init__(self, voice_path: str = settings.tts_voice):
        self.voice = PiperVoice.load(voice_path)
        self.sample_rate = self.voice.config.sample_rate

    def synthesize(self, text: str) -> np.ndarray:
        chunks = [
            np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
            for chunk in self.voice.synthesize(speakable(text))
        ]
        if not chunks:
            return np.zeros(0, dtype=np.int16)
        return np.concatenate(chunks)

    def play(self, text: str) -> float:
        """Start speaking without waiting. Returns the length of the audio in seconds."""
        audio = self.synthesize(text)
        if audio.size == 0:
            return 0.0
        sd.play(audio, self.sample_rate)
        return audio.size / self.sample_rate

    def speak(self, text: str) -> None:
        """Speak and wait until finished."""
        duration = self.play(text)
        if duration:
            # sd.wait() can hang on some Bluetooth/USB headsets,
            # so wait for the clip's known length instead
            time.sleep(duration + 0.2)
            sd.stop()

    def stop(self) -> None:
        """Cut playback immediately, e.g. when the caller interrupts."""
        sd.stop()