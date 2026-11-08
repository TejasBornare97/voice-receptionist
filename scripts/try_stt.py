import time

from receptionist.stt import SpeechToText

stt = SpeechToText()

print("Calibrating, stay quiet for a second...")
stt.calibrate()
print(f"Noise threshold: {stt.threshold:.4f}")

while True:
    print("\nListening... (say 'goodbye' to stop)")
    audio = stt.listen()
    if audio is None:
        print("Didn't hear anything.")
        continue

    start = time.perf_counter()
    text = stt.transcribe(audio)
    elapsed = time.perf_counter() - start

    print(f"You said: {text!r}  ({elapsed:.1f}s to transcribe)")
    if "goodbye" in text.lower():
        break