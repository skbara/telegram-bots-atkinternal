# Part of atkinternal. See LICENSE file for full copyright and licensing details.

"""Inline and reply keyboards."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram import KeyboardButton


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
