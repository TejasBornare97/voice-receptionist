from datetime import datetime, timedelta

from receptionist.calendar_client import TZ, GoogleCalendar

calendar = GoogleCalendar()
print("Connected to Google Calendar.")

day = datetime.now(TZ).date() + timedelta(days=1)
while day.weekday() >= 5:
    day += timedelta(days=1)

slots = calendar.free_slots(day)
print(f"Free slots on {day:%A %d %B}: " + ", ".join(s.strftime("%H:%M") for s in slots))