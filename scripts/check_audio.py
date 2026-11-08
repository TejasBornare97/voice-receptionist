import sounddevice as sd

SAMPLE_RATE = 16000
SECONDS = 3

print(sd.query_devices())
print(f"\nRecording for {SECONDS} seconds, say something...")
audio = sd.rec(int(SECONDS * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="float32")
sd.wait()

print("Playing back...")
sd.play(audio, SAMPLE_RATE)
sd.wait()