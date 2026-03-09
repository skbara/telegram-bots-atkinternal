# Part of atkinternal. See LICENSE file for full copyright and licensing details.

"""Inline and reply keyboards."""

from datetime import date, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram import KeyboardButton

from ..utils import get_weeks_for_month, month_display_name


# Main menu (reply)
BTN_CREATE = "➕ Создать слот"
BTN_EDIT = "✏️ Изменить/Удалить слот"
BTN_FREE = "📋 Свободный ресурс"
BTN_CANCEL = "Отмена"
BTN_BACK = "Назад"


def main_menu_keyboard(access_level: str | None = None):
    if access_level == "view_free_resource":
        rows = [[BTN_FREE]]
    else:
        rows = [[BTN_CREATE], [BTN_EDIT], [BTN_FREE]]
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def back_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_BACK)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def back_cancel_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_BACK), KeyboardButton(BTN_CANCEL)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def inline_list(items, prefix, callback_data_key="id", max_per_row=1):
    """
    items: list of dict with 'id' and 'name' (or similar)
    prefix: callback_data prefix, e.g. "dept"
    callback_data_key: key for id in callback_data
    Deduplicates by id so each option is shown once.
    """
    seen_ids = set()
    buttons = []
    for it in items:
        sid = it.get("id") or it.get(callback_data_key)
        if sid in seen_ids:
            continue
        seen_ids.add(sid)
        name = (it.get("name") or str(sid))[:64]
        buttons.append([
            InlineKeyboardButton(name, callback_data=f"{prefix}:{sid}")
        ])
    return InlineKeyboardMarkup(buttons)


def inline_list_with_nav(items, prefix, callback_prefix, back_step: int):
    """Inline list + row with Back and Cancel."""
    kb = inline_list(items, f"{prefix}_{callback_prefix}")
    rows = list(kb.inline_keyboard)
    rows.append([
        InlineKeyboardButton(BTN_BACK, callback_data=f"{prefix}_back:{back_step}"),
        InlineKeyboardButton(BTN_CANCEL, callback_data=f"{prefix}_cancel"),
    ])
    return InlineKeyboardMarkup(rows)


def inline_back(prefix: str, step: int):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(BTN_BACK, callback_data=f"{prefix}_back:{step}"),
    ]])


def inline_back_cancel(prefix: str, step: int):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(BTN_BACK, callback_data=f"{prefix}_back:{step}"),
        InlineKeyboardButton(BTN_CANCEL, callback_data=f"{prefix}_cancel"),
    ]])


# --- Свободный ресурс: подменю, месяцы, недели, подтверждение дат ---

FREE_PREFIX = "free"

BTN_FREE_3DAYS = "На 3 дня"
BTN_FREE_DATE = "Выбрать дату"
BTN_FREE_WEEK = "Выбрать неделю"
BTN_GET = "Получить"


def free_resource_submenu_keyboard():
    """Кнопки: На 3 дня, Выбрать дату, Выбрать неделю, Отмена."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(BTN_FREE_3DAYS, callback_data=f"{FREE_PREFIX}_3days")],
        [InlineKeyboardButton(BTN_FREE_DATE, callback_data=f"{FREE_PREFIX}_date")],
        [InlineKeyboardButton(BTN_FREE_WEEK, callback_data=f"{FREE_PREFIX}_week")],
        [InlineKeyboardButton(BTN_CANCEL, callback_data=f"{FREE_PREFIX}_cancel")],
    ])


def free_date_prompt_keyboard(back_step: int):
    """Inline Назад/Отмена для шага ввода даты (как при создании слота). back_step — шаг, на который ведёт Назад (0=подменю, 1=дата начала)."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(BTN_BACK, callback_data=f"{FREE_PREFIX}_date_back:{back_step}"),
        InlineKeyboardButton(BTN_CANCEL, callback_data=f"{FREE_PREFIX}_cancel"),
    ]])


def free_date_confirm_keyboard():
    """Получить / Назад / Отмена для шага подтверждения диапазона дат."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(BTN_GET, callback_data=f"{FREE_PREFIX}_date_get")],
        [
            InlineKeyboardButton(BTN_BACK, callback_data=f"{FREE_PREFIX}_date_back:2"),
            InlineKeyboardButton(BTN_CANCEL, callback_data=f"{FREE_PREFIX}_cancel"),
        ],
    ])


def free_months_keyboard(count: int = 6):
    """Текущий месяц + (count - 1) следующих. callback_data: free_week_month:YYYY-MM."""
    today = date.today()
    buttons = []
    for i in range(count):
        d = today.replace(day=1) + timedelta(days=32 * i)
        month_start = d.replace(day=1)
        key = month_start.strftime("%Y-%m")
        label = month_display_name(month_start.year, month_start.month)
        buttons.append([InlineKeyboardButton(label, callback_data=f"{FREE_PREFIX}_week_month:{key}")])
    buttons.append([
        InlineKeyboardButton(BTN_BACK, callback_data=f"{FREE_PREFIX}_back:0"),
        InlineKeyboardButton(BTN_CANCEL, callback_data=f"{FREE_PREFIX}_cancel"),
    ])
    return InlineKeyboardMarkup(buttons)


def free_weeks_keyboard(month_date: date):
    """Недели, пересекающие месяц. callback_data: free_week_week:YYYY-MM-DD:YYYY-MM-DD."""
    weeks = get_weeks_for_month(month_date)
    buttons = []
    for week_start, week_end in weeks:
        label = f"{week_start.strftime('%d.%m')}–{week_end.strftime('%d.%m')}"
        key = f"{week_start.isoformat()}:{week_end.isoformat()}"
        buttons.append([
            InlineKeyboardButton(label, callback_data=f"{FREE_PREFIX}_week_week:{key}")
        ])
    buttons.append([
        InlineKeyboardButton(BTN_BACK, callback_data=f"{FREE_PREFIX}_week_back:1"),
        InlineKeyboardButton(BTN_CANCEL, callback_data=f"{FREE_PREFIX}_cancel"),
    ])
    return InlineKeyboardMarkup(buttons)
