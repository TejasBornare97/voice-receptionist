import time

from receptionist.config import settings
from receptionist.stt import SpeechToText
from receptionist.tts import TextToSpeech

tts = TextToSpeech()
stt = SpeechToText()

greeting = f"Hello, you're through to {settings.business_name}. How can I help you today?"

start = time.perf_counter()
audio = tts.synthesize(greeting)
print(f"Synthesised greeting in {time.perf_counter() - start:.2f}s")
tts.speak(greeting)

print("Calibrating, stay quiet for a second...")
stt.calibrate()

while True:
    print("\nListening... (say 'goodbye' to stop)")
    audio = stt.listen()
    if audio is None:
        tts.speak("Sorry, I didn't catch that.")
        continue

    text = stt.transcribe(audio)
    print(f"You said: {text!r}")

    if "goodbye" in text.lower():
        tts.speak("Thanks for calling. Goodbye.")
        break

    tts.speak(f"You said: {text}")