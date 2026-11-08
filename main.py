import argparse

from receptionist.agent import Receptionist


def run_text() -> None:
    agent = Receptionist()
    print(f"Receptionist: {agent.greeting()}")

    while not agent.call_ended:
        caller = input("You: ").strip()
        if not caller:
            continue
        reply = agent.reply(caller)
        if reply:
            print(f"Receptionist: {reply}")


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
    while not agent.call_ended:
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
        if reply:
            print(f"Receptionist: {reply}")
            tts.speak(reply)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI voice receptionist")
    parser.add_argument("--text", action="store_true", help="type instead of speaking")
    args = parser.parse_args()

    try:
        run_text() if args.text else run_voice()
    except KeyboardInterrupt:
        print("\nCall ended.")