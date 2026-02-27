# Part of atkinternal. See LICENSE file for full copyright and licensing details.

"""Main menu, /start, Cancel, Back to menu."""

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

from ..core import clear_state, get_state, Scenario
from ..keyboards import main_menu_keyboard, BTN_BACK, BTN_CANCEL


WELCOME = (
    "Добро пожаловать. Выберите действие:"
)


def setup_menu_handlers(app, odoo):
    """Register /start and main menu handlers."""

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            WELCOME,
            reply_markup=main_menu_keyboard(),
        )

    async def cancel_or_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (update.message.text or "").strip()
        clear_state(update.effective_chat.id)
        await update.message.reply_text(
            "Действие отменено. Выберите действие:",
            reply_markup=main_menu_keyboard(),
        )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(
            filters.Regex(f"^({BTN_CANCEL}|{BTN_BACK})$"),
            cancel_or_back,
        )
    )
    return start, cancel_or_back
