import argparse

from receptionist.agent import Receptionist

END_PHRASES = ("goodbye", "good bye", "bye bye", "thats all", "thanks bye", "nothing else")


def is_goodbye(text: str) -> bool:
    # Callers and Whisper are inconsistent with apostrophes ("that's" vs "thats")
    normalised = text.lower().replace("'", "").replace("\u2019", "")
    return any(phrase in normalised for phrase in END_PHRASES)


def run_text() -> None:
    agent = Receptionist()
    print(f"Receptionist: {agent.greeting()}")

    while True:
        caller = input("You: ").strip()
        if not caller:
            continue
        print(f"Receptionist: {agent.reply(caller)}")
        if is_goodbye(caller):
            break


def run_voice() -> None:
    from receptionist.stt import SpeechToText
    from receptionist.tts import TextToSpeech

    stt = SpeechToText()
    tts = TextToSpeech()
    agent = Receptionist()

    print("Calibrating microphone, stay quiet for a second...")
    stt.calibrate()

    greeting = agent.greeting()
    print(f"Receptionist: {greeting}")
    tts.speak(greeting)

    missed = 0
    while True:
        print("(listening...)")
        audio = stt.listen()
        if audio is None:
            missed += 1
            if missed >= 2:
                tts.speak("I'll let you go. Thanks for calling, goodbye.")
                break
            tts.speak("Are you still there?")
            continue

        print("(thinking...)")
        caller = stt.transcribe(audio)
        if not caller:
            continue
        missed = 0
        print(f"Caller: {caller}")

        reply = agent.reply(caller)
        print(f"Receptionist: {reply}")
        tts.speak(reply)

        if is_goodbye(caller):
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI voice receptionist")
    parser.add_argument("--text", action="store_true", help="type instead of speaking")
    args = parser.parse_args()

    try:
        run_text() if args.text else run_voice()
    except KeyboardInterrupt:
        print("\nCall ended.")