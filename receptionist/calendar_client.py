import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from receptionist.config import settings

TZ = ZoneInfo(settings.timezone)
SLOT_LENGTH = timedelta(minutes=45)
OPENING = time(9, 0)
CLOSING = time(17, 0)


class SlotUnavailableError(Exception):
    pass


@dataclass
class Booking:
    id: str
    name: str
    phone: str
    start: datetime

    @property
    def end(self) -> datetime:
        return self.start + SLOT_LENGTH


def clinic_slots(day: date) -> list[datetime]:
    """Every bookable start time on a day, ignoring existing bookings."""
    if day.weekday() >= 5:
        return []
    slots = []
    start = datetime.combine(day, OPENING, tzinfo=TZ)
    close = datetime.combine(day, CLOSING, tzinfo=TZ)
    while start + SLOT_LENGTH <= close:
        slots.append(start)
        start += SLOT_LENGTH
    return slots


def _new_reference() -> str:
    return uuid.uuid4().hex[:6].upper()


class InMemoryCalendar:
    """Stand-in diary for development. Same interface as the Google client in Step 6."""

    def __init__(self, seed: bool = True):
        self.bookings: list[Booking] = []
        if seed:
            self._seed()

    def _seed(self) -> None:
        # Pre-book a few slots on the next working day so the diary isn't empty
        day = datetime.now(TZ).date() + timedelta(days=1)
        while day.weekday() >= 5:
            day += timedelta(days=1)
        slots = clinic_slots(day)
        for index in (1, 4, 6):  # 09:45, 12:00, 13:30
            self.bookings.append(
                Booking(_new_reference(), "Existing patient", "", slots[index])
            )

    def free_slots(self, day: date) -> list[datetime]:
        now = datetime.now(TZ)
        taken = {booking.start for booking in self.bookings}
        return [slot for slot in clinic_slots(day) if slot > now and slot not in taken]

    def book(self, start: datetime, name: str, phone: str) -> Booking:
        if start not in self.free_slots(start.date()):
            raise SlotUnavailableError(
                f"{start:%H:%M} on {start:%A %d %B} is not available"
            )
        booking = Booking(_new_reference(), name, phone, start)
        self.bookings.append(booking)
        return booking