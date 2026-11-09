import argparse

from receptionist.agent import Receptionist

# Audio reaches the speaker slightly after playback starts (more on Bluetooth),
# so keep the stricter barge-in check active a little past the clip's length
PLAYBACK_TAIL_S = 0.5


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

    # Open the mic once for the whole call so the headset settles before she speaks
    stt.start()
    try:
        print("Calibrating microphone, stay quiet for a second...")
        stt.calibrate()
        converse(stt, tts, agent)
    finally:
        stt.close()


def converse(stt, tts, agent) -> None:
    say = agent.greeting()
    print(f"Receptionist: {say}")
    missed = 0

    while not agent.call_ended:
        interrupted = False

        def barge_in() -> None:
            nonlocal interrupted
            interrupted = True
            tts.stop()
            print("(caller interrupted)")

        # Start speaking, then listen straight away so the caller can cut in
        playback = tts.play(say) + PLAYBACK_TAIL_S if say else 0.0
        print("(listening...)")
        audio = stt.listen(playback_s=playback, on_barge_in=barge_in)

        if audio is None:
            missed += 1
            if missed >= 2:
                tts.speak("I'll let you go. Thanks for calling, goodbye.")
                return
            say = "Are you still there?"
            continue

        print("(thinking...)")
        caller = stt.transcribe(audio)

        if not caller:
            if interrupted:
                # Something cut her off but it wasn't speech: carry on as a person would
                print("(false interruption, repeating)")
                continue  # `say` is unchanged, so she says it again
            say = ""
            continue

        if interrupted:
            agent.note_interruption()

        missed = 0
        print(f"Caller: {caller}")

        say = agent.reply(caller)
        if say:
            print(f"Receptionist: {say}")

    # The goodbye reply that came with end_call hasn't been played yet
    if say:
        tts.speak(say)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI voice receptionist")
    parser.add_argument("--text", action="store_true", help="type instead of speaking")
    args = parser.parse_args()

    try:
        run_text() if args.text else run_voice()
    except KeyboardInterrupt:
        print("\nCall ended.")