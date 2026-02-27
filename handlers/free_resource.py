# Part of atkinternal. See LICENSE file for full copyright and licensing details.

"""Scenario 3: Free resource report (today, tomorrow, day+2)."""

from datetime import datetime, time, timezone

from telegram import Update
from telegram.ext import ContextTypes

from .. import config
from ..core import OdooClient, get_state, Scenario
from ..handlers.access import check_access, no_access_message
from ..utils import today_tomorrow_day2, day_range_in_tz, datetime_to_odoo_str


ROLE_FOR_ALLOCATION = "Для распределения"


def setup_free_resource_handlers(app, odoo: OdooClient):
    return None


async def run(update: Update, context: ContextTypes.DEFAULT_TYPE, odoo: OdooClient):
    """Generate and send free resource report. Requires access check."""
    has_access, _ = await check_access(update, context, odoo)
    if not has_access:
        await no_access_message(update, context)
        return
    state = get_state(update.effective_chat.id)
    # Используем таймзону пользователя из Odoo; если она не задана,
    # используем DEFAULT_TZ (Europe/Moscow).
    tz_name = state.odoo_user_tz or config.DEFAULT_TZ
    today, tomorrow, day2 = today_tomorrow_day2(tz_name)
    role = odoo.get_role_by_name(ROLE_FOR_ALLOCATION)
    if not role:
        await update.message.reply_text(
            f"Роль «{ROLE_FOR_ALLOCATION}» не найдена в планировании."
        )
        return
    role_id = role["id"]
    employees = odoo.get_all_employees_with_resource()
    if not employees:
        await update.message.reply_text("Нет сотрудников с ресурсом для планирования.")
        return

    lines = []
    for emp in employees:
        resource_id = emp["resource_id"][0] if emp.get("resource_id") else None
        if not resource_id:
            continue
        name = emp.get("name") or f"ID {emp['id']}"
        # Сначала считаем статусы по дням, а уже потом решаем,
        # выводить ли сотрудника. Если нет слота для распределения
        # ни в один из дней, сотрудника пропускаем. Также не выводим
        # сотрудников, у которых во все три дня слоты полностью заняты.
        raw_statuses = []
        for day, label in [
            (today, today.strftime("%d.%m")),
            (tomorrow, tomorrow.strftime("%d.%m")),
            (day2, day2.strftime("%d.%m")),
        ]:
            status = _free_intervals_for_day(
                odoo,
                resource_id,
                role_id,
                day,
                tz_name,
            )
            raw_statuses.append((label, status))
        if all(status == "нет слота для распределения" for _, status in raw_statuses):
            continue
        # Если во все три дня статус "занят", значит есть базовый
        # слот "Для распределения", но он полностью перекрыт
        # другими слотами — такого сотрудника в отчёт не выводим.
        if all(status == "занят" for _, status in raw_statuses):
            continue
        day_results = [f"{label} - {status}" for label, status in raw_statuses]
        lines.append(f"{name}\n" + "\n".join(day_results))

    if not lines:
        await update.message.reply_text("Нет данных для отчёта.")
        return
    text = "\n\n".join(lines)
    if len(text) > 4000:
        chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)]
        for chunk in chunks:
            await update.message.reply_text(chunk)
    else:
        await update.message.reply_text(text)


def _free_intervals_for_day(
    odoo: OdooClient,
    resource_id: int,
    role_id: int,
    day,
    tz_name: str,
) -> str:
    """
    For one employee day: base = slots with role "Для распределения";
    subtract other slots; return "свободен" / "занят" / "свободен с HH:MM до HH:MM, ..."
    """
    day_start_utc, day_end_utc = day_range_in_tz(day, tz_name)
    # Slots with role "Для распределения" on this day (base availability)
    base_domain = [
        ("resource_id", "=", resource_id),
        ("role_id", "=", role_id),
        ("start_datetime", "<", datetime_to_odoo_str(day_end_utc)),
        ("end_datetime", ">", datetime_to_odoo_str(day_start_utc)),
    ]
    base_slots = odoo.slot_search_read(
        base_domain,
        fields=["start_datetime", "end_datetime"],
    )
    if not base_slots:
        return "нет слота для распределения"

    # Other slots (busy) on this day
    other_slots = odoo.slot_search_read(
        [
            ("resource_id", "=", resource_id),
            ("role_id", "!=", role_id),
            ("start_datetime", "<", datetime_to_odoo_str(day_end_utc)),
            ("end_datetime", ">", datetime_to_odoo_str(day_start_utc)),
        ],
        fields=["start_datetime", "end_datetime"],
    )
    if not other_slots:
        return "свободен"

    def parse_dt(value):
        """Parse Odoo datetime (UTC) to aware UTC datetime."""
        if isinstance(value, str):
            # Odoo XML-RPC обычно возвращает строки вида "YYYY-MM-DD HH:MM:SS" (naive UTC)
            try:
                dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                # Fallback на ISO-формат, если включены иные режимы
                dt = datetime.fromisoformat(value)
        else:
            dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    base_intervals = [
        (parse_dt(s["start_datetime"]), parse_dt(s["end_datetime"]))
        for s in base_slots
    ]
    busy_intervals = [
        (parse_dt(s["start_datetime"]), parse_dt(s["end_datetime"]))
        for s in other_slots
    ]
    free = _subtract_intervals(base_intervals, busy_intervals)
    if config.DEBUG:
        print(
            "[free_resource] day=", day,
            "tz=", tz_name,
            "base_intervals_utc=", base_intervals,
            "busy_intervals_utc=", busy_intervals,
            "free_utc=", free,
        )
    if not free:
        return "занят"
    # Normalize to day in local tz for display
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    day_start_local = datetime.combine(day, time(0, 0, 0), tzinfo=tz)
    day_end_local = datetime.combine(day, time(23, 59, 59), tzinfo=tz)
    parts = []
    for start_utc, end_utc in free:
        # Переводим интервалы из UTC в локальную таймзону пользователя (Europe/Moscow)
        start_local = start_utc.astimezone(tz)
        end_local = end_utc.astimezone(tz)
        start_local = max(start_local, day_start_local)
        end_local = min(end_local, day_end_local)
        if start_local >= end_local:
            continue
        parts.append(f"с {start_local.strftime('%H:%M')} до {end_local.strftime('%H:%M')}")
    if not parts:
        return "занят"
    if len(parts) == 1 and parts[0] == "с 00:00 до 23:59":
        return "свободен"
    return "свободен " + ", ".join(parts)


def _subtract_intervals(base: list, busy: list) -> list:
    """Subtract busy intervals from base. base and busy are lists of (start, end)."""
    result = list(base)
    for (bs, be) in busy:
        new_result = []
        for (rs, re) in result:
            if be <= rs or bs >= re:
                new_result.append((rs, re))
                continue
            if bs > rs:
                new_result.append((rs, bs))
            if be < re:
                new_result.append((be, re))
        result = new_result
    return result
