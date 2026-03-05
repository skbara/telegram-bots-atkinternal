# Part of atkinternal. See LICENSE file for full copyright and licensing details.

"""Access check: resolve Odoo user by Telegram user id."""

from typing import Optional, Tuple

from telegram import Update
from telegram.ext import ContextTypes

from ..core import OdooClient, get_state
from .. import config

NO_ACCESS_MESSAGE = "У вас нет доступа. Обратитесь к администратору."

# Technical values must match selection values in Odoo field
# res.users.x_telegram_access_level.
ACCESS_VIEW_FREE_RESOURCE = "view_free_resource"
ACCESS_MANAGE_SLOTS = "manage_slots"


async def check_access(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    odoo: OdooClient,
) -> Tuple[bool, Optional[dict]]:
    """
    Get telegram user id from update; find Odoo user.
    Returns (True, odoo_user_dict) if found, (False, None) otherwise.
    """
    user = update.effective_user
    if not user:
        return False, None
    telegram_id = str(user.id)
    odoo_user = odoo.get_user_by_telegram_id(telegram_id)
    if not odoo_user:
        return False, None
    state = get_state(update.effective_chat.id)
    state.odoo_user_id = odoo_user["id"]
    state.telegram_access_level = (
        odoo_user.get("x_telegram_access_level") or ACCESS_VIEW_FREE_RESOURCE
    )
    # Для корректного совпадения с UI Odoo используем таймзону,
    # указанную у пользователя в Odoo; если она пустая, падаем
    # обратно на DEFAULT_TZ (Europe/Moscow).
    state.odoo_user_tz = odoo_user.get("tz") or config.DEFAULT_TZ
    return True, odoo_user


async def no_access_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send standard no-access reply."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(NO_ACCESS_MESSAGE)
    else:
        await update.message.reply_text(NO_ACCESS_MESSAGE)
