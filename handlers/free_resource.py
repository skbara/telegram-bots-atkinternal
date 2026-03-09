# Part of atkinternal. See LICENSE file for full copyright and licensing details.

"""Scenario 3: Free resource report (3 days, date range, week)."""

from datetime import date, datetime, time, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

from .. import config
from ..core import OdooClient, get_state, clear_state, Scenario
from ..handlers.access import check_access, no_access_message
from ..keyboards import (
    main_menu_keyboard,
    free_resource_submenu_keyboard,
    free_date_confirm_keyboard,
    free_date_prompt_keyboard,
    free_months_keyboard,
    free_weeks_keyboard,
)
from ..utils import (
    today_tomorrow_day2,
    day_range_in_tz,
    datetime_to_odoo_str,
    parse_date_ddmmyyyy,
    date_to_ddmmyyyy,
)
from .menu import WELCOME


ROLE_FOR_ALLOCATION = "Для распределения"
FREE_PREFIX = "free"


def setup_free_resource_handlers(app, odoo: OdooClient):
    """Регистрация обработчиков свободного ресурса (подключение в main.py)."""
    return None


def _effective_message(update: Update):
    """Message to use for reply (from command or callback)."""
    if update.message:
        return update.message
    if update.callback_query and update.callback_query.message:
        return update.callback_query.message
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, odoo: OdooClient):
    """Show free resource submenu: На 3 дня / Выбрать дату / Выбрать неделю / Отмена."""
    has_access, _ = await check_access(update, context, odoo)
    if not has_access:
        await no_access_message(update, context)
        return
    state = get_state(update.effective_chat.id)
    state.scenario = Scenario.FREE_RESOURCE
    state.step = 0
    state.data = {"free_mode": None}

    msg = _effective_message(update)
    text = "Выберите вариант:"
    if update.callback_query:
        await update.callback_query.answer()
        await msg.reply_text(text, reply_markup=free_resource_submenu_keyboard())
    else:
        await msg.reply_text(text, reply_markup=free_resource_submenu_keyboard())


async def run_3days(update: Update, context: ContextTypes.DEFAULT_TYPE, odoo: OdooClient):
    """Report on next 3 days (today, tomorrow, day+2)."""
    has_access, _ = await check_access(update, context, odoo)
    if not has_access:
        await no_access_message(update, context)
        return
    state = get_state(update.effective_chat.id)
    tz_name = state.odoo_user_tz or config.DEFAULT_TZ
    today, _tomorrow, day2 = today_tomorrow_day2(tz_name)
    await _run_report_v2(update, context, odoo, today, day2)


def _build_report_lines_by_employee(
    odoo: OdooClient,
    role_id: int,
    employees: list,
    date_from: date,
    date_to: date,
    tz_name: str,
):
    """Build list of (employee_name, list of (day_label, status)) for days in range."""
    result = []
    current = date_from
    days_with_labels = []
    while current <= date_to:
        days_with_labels.append((current, current.strftime("%d.%m")))
        current += timedelta(days=1)

    for emp in employees:
        resource_id = emp["resource_id"][0] if emp.get("resource_id") else None
        if not resource_id:
            continue
        name = emp.get("name") or f"ID {emp['id']}"
        raw_statuses = []
        for day, label in days_with_labels:
            status = _free_intervals_for_day(
                odoo,
                resource_id,
                role_id,
                day,
                tz_name,
            )
            raw_statuses.append((label, status))
        if all(s == "нет слота для распределения" for _, s in raw_statuses):
            continue
        if all(s == "занят" for _, s in raw_statuses):
            continue
        result.append((name, raw_statuses))
    return result


async def _run_report_v2(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    odoo: OdooClient,
    date_from: date,
    date_to: date,
):
    """Generate free resource report for date range (by employee, same format as 3 days)."""
    state = get_state(update.effective_chat.id)
    msg = _effective_message(update)
    tz_name = state.odoo_user_tz or config.DEFAULT_TZ

    role = odoo.get_role_by_name(ROLE_FOR_ALLOCATION)
    if not role:
        await msg.reply_text(
            f"Роль «{ROLE_FOR_ALLOCATION}» не найдена в планировании.",
            reply_markup=main_menu_keyboard(state.telegram_access_level),
        )
        return
    employees = odoo.get_all_employees_with_resource()
    if not employees:
        await msg.reply_text(
            "Нет сотрудников с ресурсом для планирования.",
            reply_markup=main_menu_keyboard(state.telegram_access_level),
        )
        return

    blocks = _build_report_lines_by_employee(
        odoo,
        role["id"],
        employees,
        date_from,
        date_to,
        tz_name,
    )
    lines = [f"{name}\n" + "\n".join(f"{label} - {status}" for label, status in rows) for name, rows in blocks]

    if not lines:
        await msg.reply_text(
            "Нет данных для отчёта.",
            reply_markup=main_menu_keyboard(state.telegram_access_level),
        )
        return
    text = "\n\n".join(lines)
    if len(text) > 4000:
        chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)]
        for idx, chunk in enumerate(chunks):
            if idx == len(chunks) - 1:
                await msg.reply_text(
                    chunk,
                    reply_markup=main_menu_keyboard(state.telegram_access_level),
                )
            else:
                await msg.reply_text(chunk)
    else:
        await msg.reply_text(
            text,
            reply_markup=main_menu_keyboard(state.telegram_access_level),
        )


def _free_intervals_for_day(
    odoo: OdooClient,
    resource_id: int,
    role_id: int,
    day: date,
    tz_name: str,
) -> str:
    """
    For one employee day: base = slots with role "Для распределения";
    subtract other slots; return "свободен" / "занят" / "свободен с HH:MM до HH:MM, ..."
    """
    day_start_utc, day_end_utc = day_range_in_tz(day, tz_name)
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
        if isinstance(value, str):
            try:
                dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except ValueError:
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
    if not free:
        return "занят"
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    day_start_local = datetime.combine(day, time(0, 0, 0), tzinfo=tz)
    day_end_local = datetime.combine(day, time(23, 59, 59), tzinfo=tz)
    parts = []
    for start_utc, end_utc in free:
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
    """Subtract busy intervals from base."""
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


async def handle_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    odoo: OdooClient,
    raw_data: str,
):
    """Handle free_* callback_data."""
    query = update.callback_query
    if not query or not raw_data.startswith(FREE_PREFIX + "_"):
        return
    await query.answer()
    chat_id = update.effective_chat.id
    state = get_state(chat_id)
    msg = query.message

    if raw_data == f"{FREE_PREFIX}_cancel":
        clear_state(chat_id)
        state = get_state(chat_id)
        await msg.reply_text(
            WELCOME,
            reply_markup=main_menu_keyboard(state.telegram_access_level),
        )
        return

    if raw_data == f"{FREE_PREFIX}_3days":
        clear_state(chat_id)
        await run_3days(update, context, odoo)
        return

    if raw_data == f"{FREE_PREFIX}_date":
        state.data["free_mode"] = "date_range"
        state.step = 1
        state.data["edit_chat_id"] = chat_id
        state.data["edit_message_id"] = msg.message_id
        await msg.edit_text(
            "Выберите дату начала периода (в формате DD.MM.YYYY):",
            reply_markup=free_date_prompt_keyboard(0),
        )
        return

    if raw_data == f"{FREE_PREFIX}_date_get":
        date_from = state.data.get("date_from")
        date_to = state.data.get("date_to")
        if not date_from or not date_to:
            await msg.reply_text("Сначала укажите даты начала и окончания периода.")
            return
        clear_state(chat_id)
        await _run_report_v2(update, context, odoo, date_from, date_to)
        return

    if raw_data.startswith(f"{FREE_PREFIX}_date_back:"):
        step_back = int(raw_data.split(":")[1]) if ":" in raw_data else 2
        state.step = step_back
        if step_back == 0:
            state.data["free_mode"] = None
            state.data.pop("date_from", None)
            state.data.pop("date_to", None)
            await msg.edit_text(
                "Выберите вариант:",
                reply_markup=free_resource_submenu_keyboard(),
            )
        elif step_back == 1:
            state.data.pop("date_from", None)
            await msg.edit_text(
                "Выберите дату начала периода (в формате DD.MM.YYYY):",
                reply_markup=free_date_prompt_keyboard(0),
            )
        elif step_back == 2:
            state.data.pop("date_to", None)
            await msg.edit_text(
                "Выберите дату окончания периода (в формате DD.MM.YYYY):",
                reply_markup=free_date_prompt_keyboard(1),
            )
        return

    if raw_data == f"{FREE_PREFIX}_back:0":
        state.step = 0
        state.data["free_mode"] = None
        state.data.pop("month", None)
        state.data.pop("month_date", None)
        await msg.edit_text(
            "Выберите вариант:",
            reply_markup=free_resource_submenu_keyboard(),
        )
        return

    if raw_data.startswith(f"{FREE_PREFIX}_week_month:"):
        key = raw_data.split(":", 1)[1]
        year, month = map(int, key.split("-"))
        month_date = date(year, month, 1)
        state.data["month"] = key
        state.data["month_date"] = month_date
        state.step = 2
        await msg.edit_text(
            "Выберите неделю:",
            reply_markup=free_weeks_keyboard(month_date),
        )
        return

    if raw_data.startswith(f"{FREE_PREFIX}_week_week:"):
        part = raw_data.split(":", 1)[1]
        start_str, end_str = part.split(":", 1)
        date_from = date.fromisoformat(start_str)
        date_to = date.fromisoformat(end_str)
        clear_state(chat_id)
        await _run_report_v2(update, context, odoo, date_from, date_to)
        return

    if raw_data == f"{FREE_PREFIX}_week_back:1":
        state.step = 1
        state.data.pop("month", None)
        state.data.pop("month_date", None)
        await msg.edit_text(
            "Выберите месяц:",
            reply_markup=free_months_keyboard(),
        )
        return

    if raw_data == f"{FREE_PREFIX}_week":
        state.data["free_mode"] = "week"
        state.step = 1
        await msg.edit_text(
            "Выберите месяц:",
            reply_markup=free_months_keyboard(),
        )
        return


async def _edit_free_message(context, state, text: str, reply_markup):
    """Редактировать сообщение сценария свободного ресурса (дата/неделя)."""
    chat_id = state.data.get("edit_chat_id")
    message_id = state.data.get("edit_message_id")
    if chat_id is not None and message_id is not None:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    state,
    odoo: OdooClient,
) -> bool:
    """Handle text message in FREE_RESOURCE scenario (date range input). Returns True if consumed."""
    if state.scenario != Scenario.FREE_RESOURCE or state.data.get("free_mode") != "date_range":
        return False
    text = (update.message.text or "").strip()

    if state.step == 1:
        date_from = parse_date_ddmmyyyy(text)
        if not date_from:
            await _edit_free_message(
                context,
                state,
                "Неверный формат даты. Введите дату в формате DD.MM.YYYY:",
                free_date_prompt_keyboard(0),
            )
            return True
        state.data["date_from"] = date_from
        state.step = 2
        sent = await update.message.reply_text(
            "Выберите дату окончания периода (в формате DD.MM.YYYY):",
            reply_markup=free_date_prompt_keyboard(1),
        )
        state.data["edit_chat_id"] = update.effective_chat.id
        state.data["edit_message_id"] = sent.message_id
        return True

    if state.step == 2:
        date_to = parse_date_ddmmyyyy(text)
        if not date_to:
            await _edit_free_message(
                context,
                state,
                "Неверный формат даты. Введите дату в формате DD.MM.YYYY:",
                free_date_prompt_keyboard(1),
            )
            return True
        date_from = state.data.get("date_from")
        if date_to < date_from:
            await _edit_free_message(
                context,
                state,
                "Дата окончания не может быть раньше даты начала. Введите дату окончания:",
                free_date_prompt_keyboard(1),
            )
            return True
        state.data["date_to"] = date_to
        state.step = 3
        date_from_str = date_to_ddmmyyyy(date_from)
        date_to_str = date_to_ddmmyyyy(date_to)
        sent = await update.message.reply_text(
            f"Получить свободный ресурс с {date_from_str} по {date_to_str}?",
            reply_markup=free_date_confirm_keyboard(),
        )
        state.data["edit_chat_id"] = update.effective_chat.id
        state.data["edit_message_id"] = sent.message_id
        return True

    return False
