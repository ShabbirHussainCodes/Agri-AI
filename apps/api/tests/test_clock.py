"""farm_today: the farm's wall-calendar date, not the server's (found live 2026-10-05)."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.clock import farm_today

SOWING = date(2026, 8, 30)
UTC = timezone.utc


def test_early_morning_ist_is_already_the_next_day():
    # The saved advisory from the live run: 2026-10-04 20:24:51 UTC = 01:54 IST on 5 Oct.
    now = datetime(2026, 10, 4, 20, 24, 51, tzinfo=UTC)
    assert now.date() == date(2026, 10, 4)  # what date.today() on a UTC server said
    assert farm_today(now, offset_minutes=330) == date(2026, 10, 5)
    assert (farm_today(now, offset_minutes=330) - SOWING).days == 36  # was 35


@pytest.mark.parametrize(
    "utc_time, expected",
    [
        (datetime(2026, 10, 4, 18, 29, tzinfo=UTC), date(2026, 10, 4)),  # 23:59 IST
        (datetime(2026, 10, 4, 18, 30, tzinfo=UTC), date(2026, 10, 5)),  # 00:00 IST, the boundary
        (datetime(2026, 10, 5, 18, 29, tzinfo=UTC), date(2026, 10, 5)),
        (datetime(2026, 10, 5, 18, 30, tzinfo=UTC), date(2026, 10, 6)),
    ],
)
def test_the_day_changes_at_midnight_ist(utc_time, expected):
    assert farm_today(utc_time, offset_minutes=330) == expected


def test_any_timezone_aware_input_is_converted():
    ist = timezone(timedelta(hours=5, minutes=30))
    assert farm_today(datetime(2026, 10, 5, 1, 54, tzinfo=ist), offset_minutes=330) == date(2026, 10, 5)


def test_zero_offset_is_utc():
    assert farm_today(datetime(2026, 10, 4, 20, 24, tzinfo=UTC), offset_minutes=0) == date(2026, 10, 4)


def test_a_naive_datetime_is_refused():
    # A naive value would be silently read as local time of the server: exactly the bug.
    with pytest.raises(ValueError):
        farm_today(datetime(2026, 10, 4, 20, 24), offset_minutes=330)


def test_default_offset_comes_from_settings():
    from app.core.config import settings

    now = datetime(2026, 10, 4, 20, 24, tzinfo=UTC)
    assert farm_today(now) == farm_today(now, offset_minutes=settings.local_utc_offset_minutes)
    assert settings.local_utc_offset_minutes == 330
