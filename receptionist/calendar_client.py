import os
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from receptionist.config import settings

TZ = ZoneInfo(settings.timezone)
SLOT_LENGTH = timedelta(minutes=45)
OPENING = time(9, 0)
CLOSING = time(17, 0)

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
# Narrowest scope that lets us read and create events
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class SlotUnavailableError(Exception):
    pass


class CalendarError(Exception):
    """The calendar service couldn't be reached or returned an error."""


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


def _overlaps(slot: datetime, busy: list[tuple[datetime, datetime]]) -> bool:
    slot_end = slot + SLOT_LENGTH
    return any(slot < busy_end and slot_end > busy_start for busy_start, busy_end in busy)


class InMemoryCalendar:
    """Stand-in diary for development and tests."""

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
        busy = [(b.start, b.end) for b in self.bookings]
        return [s for s in clinic_slots(day) if s > now and not _overlaps(s, busy)]

    def book(self, start: datetime, name: str, phone: str) -> Booking:
        if start not in self.free_slots(start.date()):
            raise SlotUnavailableError(f"{start:%H:%M} on {start:%A %d %B} is not available")
        booking = Booking(_new_reference(), name, phone, start)
        self.bookings.append(booking)
        return booking


def _load_credentials() -> Credentials:
    if not os.path.exists(CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"{CREDENTIALS_FILE} not found. Download the OAuth client JSON from "
            "Google Cloud and save it in the project folder."
        )

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError:
            # Tokens for apps in "Testing" mode expire after 7 days; sign in again
            creds = None

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)

    with open(TOKEN_FILE, "w") as token:
        token.write(creds.to_json())
    return creds


class GoogleCalendar:
    """Real diary backed by a Google Calendar. Same interface as InMemoryCalendar."""

    def __init__(self, calendar_id: str = settings.google_calendar_id):
        if not calendar_id:
            raise ValueError("GOOGLE_CALENDAR_ID is not set in .env")
        self.calendar_id = calendar_id
        self.service = build(
            "calendar", "v3", credentials=_load_credentials(), cache_discovery=False
        )

    def _busy_periods(self, day: date) -> list[tuple[datetime, datetime]]:
        day_start = datetime.combine(day, time.min, tzinfo=TZ)
        day_end = day_start + timedelta(days=1)
        try:
            events = (
                self.service.events()
                .list(
                    calendarId=self.calendar_id,
                    timeMin=day_start.isoformat(),
                    timeMax=day_end.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute(num_retries=2)
                .get("items", [])
            )
        except (HttpError, OSError) as exc:
            raise CalendarError(f"Could not read the calendar: {exc}") from exc

        busy = []
        for event in events:
            if event.get("transparency") == "transparent":
                continue  # events marked "Free" don't block time
            start = event["start"].get("dateTime")
            end = event["end"].get("dateTime")
            if start is None:
                busy.append((day_start, day_end))  # all-day event blocks the whole day
            else:
                busy.append((datetime.fromisoformat(start), datetime.fromisoformat(end)))
        return busy

    def free_slots(self, day: date) -> list[datetime]:
        now = datetime.now(TZ)
        busy = self._busy_periods(day)
        return [s for s in clinic_slots(day) if s > now and not _overlaps(s, busy)]

    def book(self, start: datetime, name: str, phone: str) -> Booking:
        # Re-check right before writing: someone may have taken the slot mid-call
        if start not in self.free_slots(start.date()):
            raise SlotUnavailableError(f"{start:%H:%M} on {start:%A %d %B} is not available")

        reference = _new_reference()
        event = {
            "summary": f"Physio appointment: {name}",
            "description": f"Phone: {phone}\nReference: {reference}\nBooked by the voice receptionist",
            "start": {"dateTime": start.isoformat(), "timeZone": settings.timezone},
            "end": {"dateTime": (start + SLOT_LENGTH).isoformat(), "timeZone": settings.timezone},
        }
        try:
            self.service.events().insert(
                calendarId=self.calendar_id, body=event
            ).execute(num_retries=2)
        except (HttpError, OSError) as exc:
            raise CalendarError(f"Could not create the booking: {exc}") from exc

        return Booking(reference, name, phone, start)


def make_calendar():
    """Pick the diary backend from config."""
    if settings.calendar_backend == "google":
        return GoogleCalendar()
    return InMemoryCalendar()