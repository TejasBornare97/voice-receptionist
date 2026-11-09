from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic

from receptionist.calendar_client import make_calendar
from receptionist.config import settings
from receptionist.tools import TOOLS, ToolRunner

SYSTEM_PROMPT = """You are the receptionist at {business}, a physiotherapy clinic. \
You are speaking to a caller on the phone.

This call started on {today} ({iso_date}) at {time}.

How to speak:
- Keep replies to one or two short sentences. This is a phone call, not an email.
- Ask one question at a time.
- No lists, bullet points, emojis or markdown. Everything you write is read aloud.
- Say times the way people speak them, like "half past two" or "quarter to one".
- The caller's words come from speech recognition and may contain mistakes. \
If something doesn't make sense, ask them to repeat it rather than guessing.
- Callers sometimes talk over you. If a message says you were interrupted, \
don't repeat what you were saying. Respond to what the caller just said.

Booking:
- Appointments are 45 minutes, Monday to Friday. Start times are fixed, so \
use check_availability to see them. Never offer or agree to a time you haven't checked.
- If the caller's preferred time isn't free, offer the one or two closest free times.
- If the caller turns down the times you offer, ask whether another day would suit \
before ending the call.
- You need the caller's full name and phone number. Confirm the name as a question, \
like "Is that Sarah Jones?", and wait for a yes. If they say it's wrong, ask them to spell it.
- UK phone numbers have 11 digits and start with 0. If you have fewer, ask for the rest. \
Read numbers back in groups, like "oh seven eight six seven, oh five three, nine five two".
- Before calling book_appointment, read back the day, time, name and number, and wait for a yes.
- After booking, confirm the day and time and give the booking reference.
- Don't announce that you're checking the diary. Just check and then answer.

Other:
- If you can't help with something, offer to take a message for the team.
- Never give medical advice. If someone describes a medical emergency, tell them to call 999.
- When the caller has nothing else, say a short goodbye and call end_call in the same reply.
"""

FALLBACK_REPLY = (
    "Sorry, I'm having trouble with our system right now. "
    "Could you say that again in a moment?"
)
EMPTY_REPLY = "Sorry, could you say that again?"
INTERRUPTED_NOTE = "(The caller interrupted you before you finished speaking.) "
MAX_TOOL_ROUNDS = 5


def build_system_prompt(now: datetime) -> str:
    return SYSTEM_PROMPT.format(
        business=settings.business_name,
        today=now.strftime("%A %d %B %Y"),
        iso_date=now.strftime("%Y-%m-%d"),
        time=now.strftime("%H:%M"),
    )


class Receptionist:
    def __init__(self, client: anthropic.Anthropic | None = None, calendar=None):
        self.client = client or anthropic.Anthropic(
            api_key=settings.anthropic_api_key, timeout=15, max_retries=2
        )
        self.tools = ToolRunner(calendar or make_calendar())
        self.history: list[dict] = []
        self._interrupted = False
        # Fixed for the whole call: thinking blocks in the history are bound to
        # the exact system prompt they were produced with, so it must not change
        self.system_prompt = build_system_prompt(datetime.now(ZoneInfo(settings.timezone)))

    @property
    def call_ended(self) -> bool:
        return self.tools.call_ended

    def greeting(self) -> str:
        return f"Hello, you're through to {settings.business_name}. How can I help you today?"

    def note_interruption(self) -> None:
        """The caller cut off the last reply, so they didn't hear all of it."""
        self._interrupted = True

    def reply(self, caller_text: str) -> str:
        if self._interrupted:
            caller_text = INTERRUPTED_NOTE + caller_text
            self._interrupted = False

        # Remember where this turn started so a failure can be rolled back cleanly
        checkpoint = len(self.history)
        self.history.append({"role": "user", "content": caller_text})
        spoken: list[str] = []

        for _ in range(MAX_TOOL_ROUNDS):
            try:
                response = self.client.messages.create(
                    model=settings.llm_model,
                    max_tokens=1024,
                    system=self.system_prompt,
                    tools=TOOLS,
                    messages=self.history,
                )
            except anthropic.APIError as exc:
                print(f"[agent] API error: {exc}")
                del self.history[checkpoint:]
                return FALLBACK_REPLY

            if response.stop_reason not in ("end_turn", "tool_use"):
                print(f"[agent] stop_reason={response.stop_reason}")
            if not response.content:
                break

            self.history.append({"role": "assistant", "content": response.content})
            spoken.extend(
                block.text.strip()
                for block in response.content
                if block.type == "text" and block.text.strip()
            )

            tool_calls = [block for block in response.content if block.type == "tool_use"]
            if not tool_calls:
                break

            results = [
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": self.tools.run(call.name, call.input),
                }
                for call in tool_calls
            ]
            self.history.append({"role": "user", "content": results})

            if self.call_ended:
                break

        text = " ".join(spoken)
        if not text and not self.call_ended:
            del self.history[checkpoint:]
            return EMPTY_REPLY
        return text