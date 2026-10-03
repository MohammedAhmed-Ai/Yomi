"""Day-boundary helpers.

Completion stamps are stored in UTC but a "day" is a local concept: the calendar
date a task belongs to depends on the user's timezone, not the server's.
"""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.config import get_settings


def configured_timezone() -> ZoneInfo:
    """The user's timezone, falling back to UTC if the name is unknown."""
    try:
        return ZoneInfo(get_settings().timezone)
    except Exception:
        return ZoneInfo("UTC")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def local_date(moment: datetime | None = None) -> date:
    """The calendar date `moment` falls on in the configured timezone."""
    moment = moment or utc_now()
    return moment.astimezone(configured_timezone()).date()