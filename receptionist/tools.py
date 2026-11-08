import datetime as dt
import json

from receptionist.calendar_client import TZ, SlotUnavailableError

TOOLS = [
    {
        "name": "check_availability",
        "description": (
            "List the free appointment start times on a given date. "
            "Always call this before offering or agreeing to any time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date as YYYY-MM-DD"},
            },
            "required": ["date"],
        },
    },
    {
        "name": "book_appointment",
        "description": (
            "Book an appointment. Only call this after the caller has confirmed "
            "their name, phone number, date and time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date as YYYY-MM-DD"},
                "time": {"type": "string", "description": "Start time as HH:MM, 24-hour"},
                "name": {"type": "string", "description": "Caller's full name"},
                "phone": {"type": "string", "description": "Caller's phone number, digits only"},
            },
            "required": ["date", "time", "name", "phone"],
        },
    },
    {
        "name": "end_call",
        "description": (
            "Hang up. Call this when the caller has nothing else they need, "
            "in the same reply as your goodbye."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]


class ToolRunner:
    def __init__(self, calendar):
        self.calendar = calendar
        self.call_ended = False

    def run(self, name: str, args: dict) -> str:
        handlers = {
            "check_availability": self._check_availability,
            "book_appointment": self._book_appointment,
            "end_call": self._end_call,
        }
        handler = handlers.get(name)

        if handler is None:
            result = {"error": f"Unknown tool: {name}"}
        else:
            # Errors are returned to the model, not raised, so it can recover mid-call
            try:
                result = handler(**args)
            except SlotUnavailableError as exc:
                result = {
                    "error": str(exc),
                    "hint": "Check availability again and offer the caller another time.",
                }
            except (ValueError, TypeError) as exc:
                result = {"error": f"Invalid input: {exc}"}

        output = json.dumps(result)
        print(f"[tool] {name}({args}) -> {output}")
        return output

    def _check_availability(self, date: str) -> dict:
        day = dt.date.fromisoformat(date)
        today = dt.datetime.now(TZ).date()

        if day < today:
            return {"error": "That date is in the past."}
        if day.weekday() >= 5:
            return {"date": date, "free_slots": [], "note": "The clinic is closed at weekends."}

        free = self.calendar.free_slots(day)
        return {
            "date": date,
            "weekday": day.strftime("%A"),
            "free_slots": [slot.strftime("%H:%M") for slot in free],
        }

    def _book_appointment(self, date: str, time: str, name: str, phone: str) -> dict:
        digits = "".join(ch for ch in phone if ch.isdigit())
        if len(digits) != 11 or not digits.startswith("0"):
            return {"error": "Phone number must be 11 digits starting with 0. Ask the caller to repeat it."}

        start = dt.datetime.combine(
            dt.date.fromisoformat(date), dt.time.fromisoformat(time), tzinfo=TZ
        )
        booking = self.calendar.book(start, name.strip(), digits)
        return {
            "status": "confirmed",
            "reference": booking.id,
            "date": booking.start.strftime("%A %d %B"),
            "time": booking.start.strftime("%H:%M"),
            "name": booking.name,
        }

    def _end_call(self) -> dict:
        self.call_ended = True
        return {"status": "ending call"}