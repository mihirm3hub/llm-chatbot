import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo


_WEEKDAYS: dict[str, int] = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}

_MONTHS: dict[str, int] = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


@dataclass
class ExtractedSlots:
    intent: str | None = None  # booking|inquiry|reschedule
    date: str | None = None  # YYYY-MM-DD
    time: str | None = None  # HH:MM
    timezone: str | None = None  # IANA or UTC
    service_type: str | None = None


def merge_slots(existing: dict, incoming: dict) -> dict:
    merged = dict(existing or {})
    for key, value in (incoming or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        merged[key] = value
    return merged


def parse_timezone(text: str) -> str | None:
    tz_match = re.search(r"\b([A-Za-z]+/[A-Za-z_]+)\b", text)
    if tz_match:
        return tz_match.group(1)

    # Lightweight aliases for common user phrasing.
    lowered = (text or "").lower()
    if "london" in lowered and ("united kingdom" in lowered or re.search(r"\buk\b", lowered)):
        return "Europe/London"
    if "new york" in lowered:
        return "America/New_York"

    if re.search(r"\bUTC\b", text, flags=re.IGNORECASE):
        return "UTC"
    if re.search(r"\bGMT\b", text, flags=re.IGNORECASE):
        return "UTC"
    return None


def is_valid_timezone(tz_name: str) -> bool:
    if not tz_name or not isinstance(tz_name, str):
        return False
    try:
        ZoneInfo(tz_name)
        return True
    except Exception:
        return False


def parse_time(text: str) -> str | None:
    time_24 = re.search(r"\b((?:[01]\d|2[0-3])):([0-5]\d)\b", text)
    if time_24:
        return f"{time_24.group(1)}:{time_24.group(2)}"

    time_12 = re.search(r"\b(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*(am|pm)\b", text, flags=re.IGNORECASE)
    if time_12:
        hour = int(time_12.group(1))
        minute = int(time_12.group(2) or "0")
        ampm = time_12.group(3).lower()
        if ampm == "pm" and hour != 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"

    # compact "1pm" also matches above; keep here for readability.
    return None


def _parse_month_day_date(text: str, now_utc: datetime) -> str | None:
    m = re.search(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t)?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?\b",
        text,
        flags=re.IGNORECASE,
    )
    if not m:
        return None

    month_key = (m.group(1) or "").lower()
    month = _MONTHS.get(month_key)
    if not month:
        return None

    day = int(m.group(2))
    year = now_utc.year
    try:
        candidate = datetime(year, month, day, tzinfo=UTC).date()
    except Exception:
        return None

    if candidate < now_utc.date():
        try:
            candidate = datetime(year + 1, month, day, tzinfo=UTC).date()
        except Exception:
            return None

    return candidate.strftime("%Y-%m-%d")


def _parse_day_month_date(text: str, now_utc: datetime) -> str | None:
    # e.g. "15 feb", "15th Feb", "15 February"
    m = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t)?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
        text,
        flags=re.IGNORECASE,
    )
    if not m:
        return None

    day = int(m.group(1))
    month_key = (m.group(2) or "").lower()
    month = _MONTHS.get(month_key)
    if not month:
        return None

    year = now_utc.year
    try:
        candidate = datetime(year, month, day, tzinfo=UTC).date()
    except Exception:
        return None

    if candidate < now_utc.date():
        try:
            candidate = datetime(year + 1, month, day, tzinfo=UTC).date()
        except Exception:
            return None

    return candidate.strftime("%Y-%m-%d")


def _parse_next_weekday(text: str, now_utc: datetime) -> str | None:
    # "next tuesday" or "tuesday"
    m = re.search(
        r"\b(next\s+)?(mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:r|rs|rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b",
        text,
        flags=re.IGNORECASE,
    )
    if not m:
        return None

    weekday_raw = (m.group(2) or "").lower()
    target = _WEEKDAYS.get(weekday_raw)
    if target is None:
        return None

    today = now_utc.date()
    delta = (target - now_utc.weekday()) % 7
    if delta == 0:
        delta = 7
    # If user said "next", move to the following week's occurrence (keep weekday correct).
    if m.group(1) and delta < 7:
        delta += 7

    return (today + timedelta(days=delta)).strftime("%Y-%m-%d")


def parse_date(text: str, now_utc: datetime) -> str | None:
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if m:
        return m.group(1)

    lower = text.lower()
    if "today" in lower:
        return now_utc.date().strftime("%Y-%m-%d")
    if "tomorrow" in lower:
        return (now_utc.date() + timedelta(days=1)).strftime("%Y-%m-%d")

    return (
        _parse_month_day_date(text, now_utc)
        or _parse_day_month_date(text, now_utc)
        or _parse_next_weekday(text, now_utc)
    )


def within_business_rules(start_time_utc: datetime) -> bool:
    """Validate appointment start time against business rules.

    Rules (UTC): Mon–Fri, on the hour, 09:00–17:00, 1-hour slots.
    That means the last valid start is 16:00 (ending at 17:00).
    """

    dt = start_time_utc.astimezone(UTC)
    if dt.weekday() >= 5:
        return False
    if dt.minute != 0:
        return False
    if not (9 <= dt.hour <= 16):
        return False
    return True


def parse_local_start(slots: dict) -> tuple[datetime, str]:
    date_str = slots.get("date")
    time_str = slots.get("time")
    tz_name = (slots.get("timezone") or "UTC").strip() if isinstance(slots.get("timezone"), str) else "UTC"

    tz_name = tz_name or "UTC"
    try:
        tzinfo = ZoneInfo(tz_name)
    except Exception:
        tzinfo = ZoneInfo("UTC")
        tz_name = "UTC"

    local_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    local_time = datetime.strptime(time_str, "%H:%M").time()
    local_dt = datetime.combine(local_date, local_time).replace(tzinfo=tzinfo)
    return local_dt, tz_name


def find_alternatives(is_booked_fn, start_time_utc: datetime, tz_name: str, limit: int = 2) -> list[datetime]:
    """Find the next available slots after a conflicting time.

    Iterates forward in 1-hour steps in UTC, enforcing UTC business rules.
    Returns candidate datetimes in the user's timezone for display.
    """

    tzinfo = ZoneInfo(tz_name)
    candidates: list[datetime] = []
    cursor_utc = start_time_utc.astimezone(UTC)

    for _ in range(72):
        cursor_utc = cursor_utc + timedelta(hours=1)
        if not within_business_rules(cursor_utc):
            continue
        if is_booked_fn(cursor_utc):
            continue
        candidates.append(cursor_utc.astimezone(tzinfo))
        if len(candidates) >= limit:
            break

    return candidates
