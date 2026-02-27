# Part of atkinternal. See LICENSE file for full copyright and licensing details.

"""Date/time parsing and timezone helpers."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Tuple

from .. import config


def parse_date_ddmmyyyy(text: str) -> Optional[date]:
    """Parse DD.MM.YYYY; return date or None."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, config.DATE_FORMAT).date()
    except ValueError:
        return None


def date_to_ddmmyyyy(d: date) -> str:
    """Format date as DD.MM.YYYY."""
    return d.strftime(config.DATE_FORMAT)


# Odoo expects datetime as "YYYY-MM-DD HH:MM:SS", not ISO with "T"
ODOO_DATETIME_FMT = "%Y-%m-%d %H:%M:%S"


def datetime_to_odoo_str(dt: datetime) -> str:
    """Format naive datetime for Odoo (planning.slot, domain search)."""
    return dt.strftime(ODOO_DATETIME_FMT)


def build_datetime_utc(
    d: date,
    time_str: str,
    tz_name: Optional[str] = None,
) -> Optional[datetime]:
    """
    Build datetime in UTC for given date and time string (HH:MM or HH:MM:SS).
    If tz_name is given, interpret date+time in that timezone and convert to UTC.
    """
    time_str = (time_str or "").strip()
    if not time_str:
        return None
    parts = time_str.split(":")
    hour = int(parts[0]) if len(parts) > 0 else 0
    minute = int(parts[1]) if len(parts) > 1 else 0
    second = int(parts[2]) if len(parts) > 2 else 0
    try:
        t = time(hour, minute, second)
        dt_naive = datetime.combine(d, t)
    except (ValueError, IndexError):
        return None

    if tz_name:
        try:
            import zoneinfo
            z = zoneinfo.ZoneInfo(tz_name)
            dt_naive = dt_naive.replace(tzinfo=z)
            return dt_naive.astimezone(timezone.utc).replace(tzinfo=None)
        except Exception:
            pass
    # No tz or error: treat as UTC
    return dt_naive


def build_slot_start_end_utc(
    start_date: date,
    end_date: date,
    tz_name: Optional[str],
    start_time: str = "08:00",
    end_time: str = "17:00",
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Return (start_datetime_utc, end_datetime_utc) for planning.slot.
    Uses start_date + start_time, end_date + end_time in user tz, then to UTC.
    """
    start_dt = build_datetime_utc(start_date, start_time, tz_name)
    end_dt = build_datetime_utc(end_date, end_time, tz_name)
    return start_dt, end_dt


def day_range_in_tz(day: date, tz_name: Optional[str]) -> Tuple[datetime, datetime]:
    """
    Return (start, end) of the day in UTC (naive datetimes).
    Day is [00:00:00, 23:59:59] in the given timezone.
    """
    if tz_name:
        try:
            import zoneinfo
            z = zoneinfo.ZoneInfo(tz_name)
            start = datetime.combine(day, time(0, 0, 0), tzinfo=z)
            end = datetime.combine(day, time(23, 59, 59), tzinfo=z)
            start_utc = start.astimezone(timezone.utc).replace(tzinfo=None)
            end_utc = end.astimezone(timezone.utc).replace(tzinfo=None)
            return start_utc, end_utc
        except Exception:
            pass
    start = datetime.combine(day, time(0, 0, 0))
    end = datetime.combine(day, time(23, 59, 59))
    return start, end


def today_tomorrow_day2(tz_name: Optional[str]) -> Tuple[date, date, date]:
    """Return (today, tomorrow, day_after_tomorrow) in the given timezone."""
    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            z = ZoneInfo(tz_name)
            now = datetime.now(z).date()
            return now, now + timedelta(days=1), now + timedelta(days=2)
        except Exception:
            pass
    now = datetime.now(timezone.utc).date()
    return now, now + timedelta(days=1), now + timedelta(days=2)
