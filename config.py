# Part of atkinternal. See LICENSE file for full copyright and licensing details.

"""Configuration from environment variables."""

import os


def _str(value):
    return (value or "").strip() or None


def _bool(value):
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


# Odoo
ODOO_URL = _str(os.environ.get("ODOO_URL")) or "http://localhost:8069"
ODOO_DB = _str(os.environ.get("ODOO_DB")) or "odoo"
ODOO_BOT_LOGIN = _str(os.environ.get("ODOO_BOT_LOGIN")) or "admin"
ODOO_BOT_PASSWORD = _str(os.environ.get("ODOO_BOT_PASSWORD")) or ""

# Telegram
BOT_TOKEN = _str(os.environ.get("BOT_TOKEN")) or ""

# Telegram API request timeouts (seconds; default 5 in library often too low)
def _float(value, default):
    if value is None:
        return default
    try:
        return float(str(value).strip())
    except ValueError:
        return default


REQUEST_READ_TIMEOUT = _float(os.environ.get("BOT_REQUEST_READ_TIMEOUT"), 30.0)
REQUEST_WRITE_TIMEOUT = _float(os.environ.get("BOT_REQUEST_WRITE_TIMEOUT"), 30.0)
REQUEST_CONNECT_TIMEOUT = _float(os.environ.get("BOT_REQUEST_CONNECT_TIMEOUT"), 30.0)

# Optional
DEBUG = _bool(os.environ.get("BOT_DEBUG", "0"))

# Default slot times (README: 08:00 - 17:00)
DEFAULT_SLOT_START_TIME = "08:00"
DEFAULT_SLOT_END_TIME = "17:00"

# Date format in Telegram
DATE_FORMAT = "%d.%m.%Y"
DATE_FORMAT_HINT = "DD.MM.YYYY"

# Default timezone for Odoo and all users
DEFAULT_TZ = "Europe/Moscow"
