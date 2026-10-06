"""The farm's calendar date.

"Today" for a farmer is the date on the farmer's wall calendar, not the date on the server. A Cloud
Run container runs in UTC, so between 00:00 and 05:30 IST its `date.today()` is still yesterday: a crop
sown on 30 Aug read "35 days" on the morning of 5 Oct, where the farmer's calendar says 36 (found in the
first live run, 2026-10-05; the saved advisory's created_at was 01:54 IST).

AgriAI serves India, which has one time zone and no daylight saving, so a fixed offset is exact and needs
no tz database (a slim container image may not ship one). It is a setting
(`AGRIAI_LOCAL_UTC_OFFSET_MINUTES`, default 330) rather than a constant because region is a config
concern in this architecture. The water balance does not use this: it takes the farm's local date from
the weather response, which is derived from the farm's coordinates.
"""
from datetime import date, datetime, timedelta, timezone


def farm_today(now: datetime | None = None, *, offset_minutes: int | None = None) -> date:
    """The calendar date at the farm. `now` (timezone-aware) and `offset_minutes` exist so tests
    need neither a clock nor environment variables."""
    if offset_minutes is None:
        from app.core.config import settings  # lazy: Settings() needs environment variables

        offset_minutes = settings.local_utc_offset_minutes
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("farm_today needs a timezone-aware datetime")
    return now.astimezone(timezone(timedelta(minutes=offset_minutes))).date()
