import queue
from collections import deque
from typing import Callable

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from receptionist.config import settings

BLOCK_MS = 30
BLOCK_SIZE = int(settings.sample_rate * BLOCK_MS / 1000)

# Barge-in tuning: while the receptionist is talking, the caller must be this
# many times louder than the normal threshold, for most of a short window,
# before we treat it as an interruption rather than echo or a cough
BARGE_IN_SENSITIVITY = 3.5
BARGE_IN_WINDOW = 15  # blocks (~450 ms)
BARGE_IN_REQUIRED = 12  # loud blocks within the window (~360 ms of speech)

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
        self._blocks: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: sd.InputStream | None = None

    # The microphone stays open for the whole call. Opening it per turn makes
    # Bluetooth headsets switch audio mode, which clips the start of playback.

    def start(self) -> None:
        if self._stream is None:
            self._stream = sd.InputStream(
                samplerate=settings.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=BLOCK_SIZE,
                callback=self._on_audio,
            )
            self._stream.start()

    def close(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _on_audio(self, indata, frames, time_info, status) -> None:
        self._blocks.put(indata[:, 0].copy())

    def _drain(self) -> None:
        """Discard audio captured before this point."""
        while True:
            try:
                self._blocks.get_nowait()
            except queue.Empty:
                return

    def _next_block(self) -> np.ndarray:
        try:
            # Never wait forever: if the device stops sending audio, fail loudly
            return self._blocks.get(timeout=3)
        except queue.Empty:
            raise MicrophoneError(
                "No audio from the microphone for 3 seconds. "
                "Check the input device in Windows sound settings."
            )

    def calibrate(self, seconds: float = 1.0) -> None:
        """Measure background noise so speech detection adapts to the room."""
        self.start()
        self._drain()
        count = int(seconds * 1000 / BLOCK_MS)
        audio = np.concatenate([self._next_block() for _ in range(count)])
        self.threshold = max(_rms(audio) * 3, 0.005)

    def listen(
        self,
        silence_ms: int = 800,
        start_timeout_s: float = 10,
        max_seconds: float = 15,
        playback_s: float = 0.0,
        on_barge_in: Callable[[], None] | None = None,
    ) -> np.ndarray | None:
        """Record one utterance. Returns None if the caller says nothing.

        If playback_s > 0, listening starts while the receptionist is still
        talking, and on_barge_in is called if the caller talks over her.
        """
        self.start()
        self._drain()

        # Keep ~600 ms before speech starts so the first syllable isn't clipped
        pre_roll: deque[np.ndarray] = deque(maxlen=20)
        recent_loud: deque[bool] = deque(maxlen=BARGE_IN_WINDOW)
        recorded: list[np.ndarray] = []
        speaking = False
        quiet_blocks = 0
        waited_blocks = 0
        elapsed_blocks = 0

        silence_limit = silence_ms // BLOCK_MS
        start_limit = int(start_timeout_s * 1000 / BLOCK_MS)
        max_blocks = int(max_seconds * 1000 / BLOCK_MS)
        playback_blocks = int(playback_s * 1000 / BLOCK_MS)
        barge_threshold = self.threshold * BARGE_IN_SENSITIVITY

        while True:
            block = self._next_block()
            elapsed_blocks += 1
            level = _rms(block)

            if not speaking:
                pre_roll.append(block)

                if elapsed_blocks <= playback_blocks:
                    # Receptionist is still talking: only sustained, loud speech counts
                    recent_loud.append(level > barge_threshold)
                    if sum(recent_loud) >= BARGE_IN_REQUIRED:
                        speaking = True
                        recorded.extend(pre_roll)
                        if on_barge_in:
                            on_barge_in()
                    continue

                # Normal listening after playback has finished
                if level > self.threshold:
                    speaking = True
                    recorded.extend(pre_roll)
                else:
                    waited_blocks += 1
                    if waited_blocks >= start_limit:
                        return None
                continue

            recorded.append(block)
            quiet_blocks = 0 if level > self.threshold else quiet_blocks + 1
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