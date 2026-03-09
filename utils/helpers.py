# Part of atkinternal. See LICENSE file for full copyright and licensing details.

"""Date/time parsing and timezone helpers."""

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, Tuple, Union

# Названия месяцев на русском (для кнопок «Март 2026»)
MONTH_NAMES_RU = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)

from .. import config

# Формат быстрого слота: Проект-Роль-Начало(DD.MM.YYYY)-Конец(DD.MM.YYYY)-Доп.текст
QUICK_SLOT_DATE_PATTERN = re.compile(r"\d{2}\.\d{2}\.\d{4}")


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


def month_display_name(year: int, month: int) -> str:
    """Format month for display, e.g. 'Март 2026'."""
    if 1 <= month <= 12:
        return f"{MONTH_NAMES_RU[month - 1]} {year}"
    return f"{month:02d}.{year}"


def get_weeks_for_month(month_date: date) -> List[Tuple[date, date]]:
    """
    Return list of (week_start, week_end) for all calendar weeks
    (Monday–Sunday) that intersect the given month.
    week_start = Monday, week_end = Sunday.
    """
    first_day = month_date.replace(day=1)
    last_day = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1)
    last_day = last_day - timedelta(days=1)
    # Понедельник недели, в которую входит первый день месяца
    monday = first_day - timedelta(days=first_day.weekday())
    weeks = []
    while monday <= last_day:
        week_end = monday + timedelta(days=6)
        if week_end >= first_day:
            weeks.append((monday, week_end))
        monday += timedelta(days=7)
    return weeks


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


def parse_quick_slot_parts(
    text: str,
) -> Union[
    Tuple[str, date, date, str],
    Tuple[None, None, None, None, str],
]:
    """
    Разбирает строку быстрого формата:
    Проект-Роль-Начало(DD.MM.YYYY)-Конец(DD.MM.YYYY)-Доп.текст
    Названия проектов и ролей могут содержать «-», поэтому разделение идёт по
    позициям двух дат DD.MM.YYYY.

    Возвращает либо (project_role_str, start_date, end_date, name),
    либо (None, None, None, None, error_message).
    """
    text = (text or "").strip()
    if not text:
        return (None, None, None, None, "Введите непустую строку в быстром формате.")

    matches = list(QUICK_SLOT_DATE_PATTERN.finditer(text))
    if len(matches) < 2:
        return (
            None,
            None,
            None,
            None,
            "Неверный формат: в строке должны быть две даты в формате DD.MM.YYYY. Проверьте данные и попробуйте еще раз.",
        )
    if len(matches) > 2:
        return (
            None,
            None,
            None,
            None,
            "Неверный формат: найдено больше двух дат. Укажите ровно две даты DD.MM.YYYY и попробуйте еще раз.",
        )

    first = matches[0]
    second = matches[1]
    start_str = first.group(0)
    end_str = second.group(0)

    start_date = parse_date_ddmmyyyy(start_str)
    end_date = parse_date_ddmmyyyy(end_str)
    if not start_date:
        return (
            None,
            None,
            None,
            None,
            f"Неверный формат даты начала: «{start_str}». Ожидается DD.MM.YYYY.",
        )
    if not end_date:
        return (
            None,
            None,
            None,
            None,
            f"Неверный формат даты окончания: «{end_str}». Ожидается DD.MM.YYYY.",
        )
    if end_date < start_date:
        return (
            None,
            None,
            None,
            None,
            "Дата окончания не может быть раньше даты начала. Попробуйте еще раз.",
        )

    before_first = text[: first.start()].rstrip("-").strip()
    after_second = text[second.end() :].lstrip("-").strip()

    if not before_first:
        return (
            None,
            None,
            None,
            None,
            "Неверный формат: до первой даты должно быть указано: Проект-Роль.",
        )

    return (before_first, start_date, end_date, after_second or "Слот")


def resolve_project_and_role(
    project_role_str: str,
    projects: List[dict],
    roles: List[dict],
) -> Union[Tuple[int, Optional[int], Optional[str]], Tuple[None, None, str]]:
    """
    Разделяет строку «Проект-Роль» на проект и роль по совпадению с Odoo.
    Роль ищется с конца строки (названия проектов могут содержать «-»).
    Принимаются только полные совпадения имени проекта и имени роли (вхождение не используется).

    projects/roles: list of dict with "id", "name".
    Возвращает (project_id, role_id, None) или (None, None, error_message).
    project_id может быть False для «Без проекта» — не поддерживается в быстром формате.
    """
    project_role_str = (project_role_str or "").strip()
    if not project_role_str:
        return (None, None, "Не указаны проект и роль.")

    # Сортируем роли по длине имени по убыванию, чтобы сначала пробовать длинные совпадения
    roles_sorted = sorted(
        (r for r in roles if (r.get("name") or "").strip()),
        key=lambda r: len((r["name"] or "").strip()),
        reverse=True,
    )
    for role in roles_sorted:
        rname = (role["name"] or "").strip()
        if not rname:
            continue
        # Строка должна заканчиваться на роль (с возможным разделителем «-» перед ней)
        normalized = project_role_str.strip()
        if normalized == rname:
            project_part = ""
        elif normalized.endswith("-" + rname):
            project_part = normalized[: -len(rname) - 1].rstrip("-").strip()
        elif normalized.endswith(" " + rname):
            project_part = normalized[: -len(rname) - 1].rstrip("-").strip()
        else:
            continue
        # Ищем проект только по полному совпадению имени (вхождение не используется)
        project_part = project_part.strip()
        if not project_part:
            return (None, None, "Не указано название проекта.")
        for proj in projects:
            pname = (proj.get("name") or "").strip()
            if not pname:
                continue
            if pname == project_part:
                return (proj["id"], role["id"], None)
        return (
            None,
            None,
            f"Проект «{project_part}» не найден в Odoo. Проверьте название и попробуйте еще раз.",
        )

    return (
        None,
        None,
        "Роль не найдена в Odoo. Проверьте данные и попробуйте еще раз.",
    )
