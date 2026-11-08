from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic

from receptionist.config import settings

SYSTEM_PROMPT = """You are the receptionist at {business}, a physiotherapy clinic. \
You are speaking to a caller on the phone.

Today is {today}. The time is {time}.

How to speak:
- Keep replies to one or two short sentences. This is a phone call, not an email.
- Ask one question at a time.
- No lists, bullet points, emojis or markdown. Everything you write is read aloud.
- Say times the way people speak them, like "half past two" or "ten in the morning".
- The caller's words come from speech recognition and may contain mistakes. \
If something doesn't make sense, ask them to repeat it rather than guessing.

What you do:
- Help callers book physiotherapy appointments. Appointments are 45 minutes, \
Monday to Friday, between 9am and 5pm.
- To book, you need the caller's full name, their preferred day and time, and a phone number.
- Read the caller's name back to confirm it. Only ask them to spell it if they say it's wrong.
- UK mobile numbers have 11 digits and start with 07. If you have fewer than 11 digits, \
ask for the rest. Read numbers back in groups, for example "oh seven eight six seven, \
oh five three, nine five two".
- You can't check the diary yet. If asked about availability, take their preferred \
time and say you'll confirm it.
- If you can't help with something, offer to take a message for the team.
- Never give medical advice. If someone describes a medical emergency, tell them to call 999.
"""

FALLBACK_REPLY = (
    "Sorry, I'm having trouble with our system right now. "
    "Could you say that again in a moment?"
)
EMPTY_REPLY = "Sorry, could you say that again?"


class Receptionist:
    def __init__(self, client: anthropic.Anthropic | None = None):
        self.client = client or anthropic.Anthropic(
            api_key=settings.anthropic_api_key, timeout=15, max_retries=2
        )
        self.history: list[dict] = []

    def greeting(self) -> str:
        return f"Hello, you're through to {settings.business_name}. How can I help you today?"

    def _system_prompt(self) -> str:
        now = datetime.now(ZoneInfo(settings.timezone))
        return SYSTEM_PROMPT.format(
            business=settings.business_name,
            today=now.strftime("%A %d %B %Y"),
            time=now.strftime("%H:%M"),
        )

    def reply(self, caller_text: str) -> str:
        self.history.append({"role": "user", "content": caller_text})

        try:
            response = self.client.messages.create(
                model=settings.llm_model,
                # Generous ceiling: the model may reason before answering, and that
                # counts toward this limit. Brevity is enforced by the prompt instead.
                max_tokens=1024,
                system=self._system_prompt(),
                messages=self.history,
            )
        except anthropic.APIError as exc:
            print(f"[agent] API error: {exc}")
            # Drop the failed turn so the caller can simply repeat themselves
            self.history.pop()
            return FALLBACK_REPLY

        if response.stop_reason != "end_turn":
            print(f"[agent] stop_reason={response.stop_reason}")

        text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()

        if not text:
            # Never store an empty turn; it confuses the rest of the conversation
            self.history.pop()
            return EMPTY_REPLY

        self.history.append({"role": "assistant", "content": text})
        return text