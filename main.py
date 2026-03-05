# Part of atkinternal. See LICENSE file for full copyright and licensing details.

"""Entry point: run Telegram bot with long polling."""

import logging
import sys

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.request import HTTPXRequest

from . import config
from .core import OdooClient, get_state, clear_state, Scenario
from .keyboards import main_menu_keyboard, BTN_CREATE, BTN_EDIT, BTN_FREE
from .handlers.access import (
    check_access,
    no_access_message,
    ACCESS_MANAGE_SLOTS,
)
from .handlers.menu import setup_menu_handlers
from .handlers.create_slot import start as create_start, handle_callback as create_cb, handle_message as create_msg
from .handlers.edit_slot import start as edit_start, handle_callback as edit_cb, handle_message as edit_msg
from .handlers.free_resource import run as free_run


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG if config.DEBUG else logging.INFO,
)
logger = logging.getLogger(__name__)


def run():
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN is not set")
        sys.exit(1)
    odoo = OdooClient()
    if not odoo.authenticate():
        logger.error("Odoo authentication failed (check ODOO_URL, ODOO_DB, ODOO_BOT_LOGIN, ODOO_BOT_PASSWORD)")
        sys.exit(1)

    request = HTTPXRequest(
        read_timeout=config.REQUEST_READ_TIMEOUT,
        write_timeout=config.REQUEST_WRITE_TIMEOUT,
        connect_timeout=config.REQUEST_CONNECT_TIMEOUT,
    )
    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .request(request)
        .build()
    )

    async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        allowed, _ = await check_access(update, context, odoo)
        if not allowed:
            await no_access_message(update, context)
            return
        state = get_state(update.effective_chat.id)
        text = (update.message.text or "").strip()
        if text == BTN_CREATE:
            if state.telegram_access_level == ACCESS_MANAGE_SLOTS:
                await create_start(update, context, odoo)
            else:
                await update.message.reply_text(
                    "У вас нет прав для создания слотов. Обратитесь к администратору.",
                    reply_markup=main_menu_keyboard(state.telegram_access_level),
                )
            return
        if text == BTN_EDIT:
            if state.telegram_access_level == ACCESS_MANAGE_SLOTS:
                await edit_start(update, context, odoo)
            else:
                await update.message.reply_text(
                    "У вас нет прав для изменения или удаления слотов. Обратитесь к администратору.",
                    reply_markup=main_menu_keyboard(state.telegram_access_level),
                )
            return
        if text == BTN_FREE:
            await free_run(update, context, odoo)
            return
        if state.scenario == Scenario.CREATE_SLOT:
            consumed = await create_msg(update, context, state, odoo)
            if consumed:
                return
        if state.scenario == Scenario.EDIT_SLOT:
            consumed = await edit_msg(update, context, state, odoo)
            if consumed:
                return
        await update.message.reply_text(
            "Выберите действие:",
            reply_markup=main_menu_keyboard(state.telegram_access_level),
        )

    async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query or not query.data:
            return
        allowed, _ = await check_access(update, context, odoo)
        if not allowed:
            await no_access_message(update, context)
            return
        data = query.data
        parts = data.split(":")
        prefix = parts[0].split("_")[0] if "_" in parts[0] else parts[0]
        if prefix == "create":
            await create_cb(update, context, odoo, data.split("_")[-1].split(":") if "_" in data else [data])
            return
        if prefix == "edit":
            await edit_cb(update, context, odoo, data.split("_")[-1].split(":") if "_" in data else [data])
            return

    async def callback_handler_fixed(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if not query or not query.data:
            return
        allowed, _ = await check_access(update, context, odoo)
        if not allowed:
            await no_access_message(update, context)
            return
        raw = query.data
        if raw.startswith("create_"):
            rest = raw[7:]
            parts = rest.split(":", 1) if ":" in rest else [rest]
            await create_cb(update, context, odoo, parts)
            return
        if raw.startswith("edit_"):
            rest = raw[5:]
            parts = rest.split(":", 1) if ":" in rest else [rest]
            await edit_cb(update, context, odoo, parts)
            return

    setup_menu_handlers(app, odoo)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler),
    )
    app.add_handler(CallbackQueryHandler(callback_handler_fixed))

    logger.info("Bot starting (long polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run()
