import queue
from collections import deque

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from receptionist.config import settings

BLOCK_MS = 30
BLOCK_SIZE = int(settings.sample_rate * BLOCK_MS / 1000)

# Primes Whisper with the vocabulary of the call, which improves
# accuracy on digits, times and booking words
CALL_CONTEXT = (
    "A caller is booking a physiotherapy appointment by phone. "
    "They give their name, a day and time such as half past one, "
    "quarter past eleven or quarter to one, "
    "and a UK phone number such as 07700 900123."
)


def _rms(block: np.ndarray) -> float:
    return float(np.sqrt(np.mean(block**2)))


class MicrophoneError(RuntimeError):
    pass


class SpeechToText:
    def __init__(self, model_size: str = settings.whisper_model):
        # int8 on CPU keeps it fast enough for live conversation without a GPU
        self.model = WhisperModel(
            model_size, device="cpu", compute_type="int8", download_root="models"
        )
        self.threshold = 0.01

    def calibrate(self, seconds: float = 1.0) -> None:
        """Measure background noise so speech detection adapts to the room."""
        audio = sd.rec(
            int(seconds * settings.sample_rate),
            samplerate=settings.sample_rate,
            channels=1,
            dtype="float32",
        )
        sd.wait()
        self.threshold = max(_rms(audio) * 3, 0.005)

    def listen(
        self,
        silence_ms: int = 800,
        start_timeout_s: float = 10,
        max_seconds: float = 15,
    ) -> np.ndarray | None:
        """Record one utterance. Returns None if the caller says nothing."""
        blocks: queue.Queue[np.ndarray] = queue.Queue()

        def on_audio(indata, frames, time_info, status):
            blocks.put(indata[:, 0].copy())

        # Keep ~300 ms before speech starts so the first syllable isn't clipped
        pre_roll: deque[np.ndarray] = deque(maxlen=10)
        recorded: list[np.ndarray] = []
        speaking = False
        quiet_blocks = 0
        waited_blocks = 0

        silence_limit = silence_ms // BLOCK_MS
        start_limit = int(start_timeout_s * 1000 / BLOCK_MS)
        max_blocks = int(max_seconds * 1000 / BLOCK_MS)

        with sd.InputStream(
            samplerate=settings.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=BLOCK_SIZE,
            callback=on_audio,
        ):
            while True:
                try:
                    # Never wait forever: if the device stops sending audio, fail loudly
                    block = blocks.get(timeout=3)
                except queue.Empty:
                    raise MicrophoneError(
                        "No audio from the microphone for 3 seconds. "
                        "Check the input device in Windows sound settings."
                    )

                loud = _rms(block) > self.threshold

                if not speaking:
                    if loud:
                        speaking = True
                        recorded.extend(pre_roll)
                        recorded.append(block)
                    else:
                        pre_roll.append(block)
                        waited_blocks += 1
                        if waited_blocks >= start_limit:
                            return None
                    continue

                recorded.append(block)
                quiet_blocks = 0 if loud else quiet_blocks + 1
                if quiet_blocks >= silence_limit or len(recorded) >= max_blocks:
                    break

        return np.concatenate(recorded)

    def transcribe(self, audio: np.ndarray) -> str:
        segments, _ = self.model.transcribe(
            audio,
            language="en",
            beam_size=1,
            vad_filter=True,
            initial_prompt=CALL_CONTEXT,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()