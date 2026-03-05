# Part of atkinternal. See LICENSE file for full copyright and licensing details.

"""Scenario 1: Create planning.slot."""

from telegram import Update
from telegram.ext import ContextTypes
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from .. import config
from ..core import OdooClient, get_state, clear_state, Scenario
from ..keyboards import (
    inline_list,
    inline_list_with_nav,
    inline_back_cancel,
    back_cancel_keyboard,
    main_menu_keyboard,
    BTN_CANCEL,
)
from ..utils import (
    parse_date_ddmmyyyy,
    build_slot_start_end_utc,
    datetime_to_odoo_str,
)
from .menu import WELCOME


CREATE_PREFIX = "create"


def setup_create_slot_handlers(app, odoo: OdooClient):
    """Register create-slot handlers. Callbacks routed from main."""
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, odoo: OdooClient):
    """Start create-slot flow: show departments."""
    state = get_state(update.effective_chat.id)
    state.scenario = Scenario.CREATE_SLOT
    state.step = 1
    state.data = {}
    depts = odoo.get_departments()
    if not depts:
        await update.message.reply_text(
            "Нет отделов. Обратитесь к администратору.",
            reply_markup=back_cancel_keyboard(),
        )
        return
    # На первом шаге есть только выбор отдела и кнопка «Отмена».
    base_kb = inline_list(depts, f"{CREATE_PREFIX}_dept")
    rows = list(base_kb.inline_keyboard)
    rows.append(
        [InlineKeyboardButton(BTN_CANCEL, callback_data=f"{CREATE_PREFIX}_cancel")]
    )
    await update.message.reply_text(
        "Выберите отдел:",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def handle_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    odoo: OdooClient,
    parts: list,
):
    """Handle callback_data: create_dept:id, create_emp:id, create_role:id, create_proj:id, create_back:n, create_cancel."""
    query = update.callback_query
    await query.answer()
    state = get_state(update.effective_chat.id)
    chat_id = update.effective_chat.id

    if parts[0] == "cancel":
        clear_state(chat_id)
        await query.edit_message_text(
            WELCOME,
            reply_markup=InlineKeyboardMarkup([]),
        )
        return

    if parts[0] == "back":
        step_back = int(parts[1]) if len(parts) > 1 else 1
        state.step = step_back
        if step_back == 0:
            clear_state(chat_id)
            await query.edit_message_text(
                WELCOME,
                reply_markup=InlineKeyboardMarkup([]),
            )
            return
        # Show previous step depending on target step
        if step_back == 1:
            # Вернуться к начальному шагу (выбор отдела, только «Отмена»)
            depts = odoo.get_departments()
            base_kb = inline_list(depts, f"{CREATE_PREFIX}_dept")
            rows = list(base_kb.inline_keyboard)
            rows.append(
                [
                    InlineKeyboardButton(
                        BTN_CANCEL, callback_data=f"{CREATE_PREFIX}_cancel"
                    )
                ]
            )
            await query.edit_message_text(
                "Выберите отдел:",
                reply_markup=InlineKeyboardMarkup(rows),
            )
            return
        if step_back == 2:
            # Back to employee selection within chosen department
            department_id = state.data.get("department_id")
            if not department_id:
                depts = odoo.get_departments()
                await query.edit_message_text(
                    "Выберите отдел:",
                    reply_markup=inline_list_with_nav(depts, CREATE_PREFIX, "dept", 1),
                )
                state.step = 1
                return
            employees = odoo.get_employees_by_department(department_id)
            await query.edit_message_text(
                "Выберите сотрудника:",
                reply_markup=inline_list_with_nav(employees, CREATE_PREFIX, "emp", 1),
            )
            return
        if step_back == 3:
            # Back to role selection
            roles = odoo.get_planning_roles()
            await query.edit_message_text(
                "Выберите роль:",
                reply_markup=inline_list_with_nav(roles, CREATE_PREFIX, "role", 2),
            )
            return
        if step_back == 4:
            # Back to project selection
            projects = odoo.get_projects()
            await query.edit_message_text(
                "Выберите проект:",
                reply_markup=inline_list_with_nav(
                    projects if projects else [{"id": False, "name": "— Без проекта —"}],
                    CREATE_PREFIX,
                    "proj",
                    3,
                ),
            )
            return
        if step_back == 5:
            # Back to start date input
            await query.edit_message_text(
                f"Введите дату начала в формате {config.DATE_FORMAT_HINT} (время 08:00):",
                reply_markup=inline_back_cancel(CREATE_PREFIX, 4),
            )
            return
        if step_back == 6:
            # Back to end date input
            await query.edit_message_text(
                f"Введите дату окончания в формате {config.DATE_FORMAT_HINT} (время 17:00):",
                reply_markup=inline_back_cancel(CREATE_PREFIX, 5),
            )
            return
        return

    if parts[0] == "dept" and len(parts) >= 2:
        state.data["department_id"] = int(parts[1])
        state.step = 2
        employees = odoo.get_employees_by_department(state.data["department_id"])
        if not employees:
            await query.edit_message_text(
                "В отделе нет сотрудников с ресурсом для планирования.",
                reply_markup=inline_back_cancel(CREATE_PREFIX, 1),
            )
            return
        await query.edit_message_text(
            "Выберите сотрудника:",
            reply_markup=inline_list_with_nav(employees, CREATE_PREFIX, "emp", 1),
        )
        return

    if parts[0] == "emp" and len(parts) >= 2:
        state.data["employee_id"] = int(parts[1])
        emps = odoo.get_employees_by_department(state.data["department_id"])
        emp = next((e for e in emps if e["id"] == state.data["employee_id"]), None)
        if emp and emp.get("resource_id"):
            state.data["resource_id"] = emp["resource_id"][0]
        state.step = 3
        roles = odoo.get_planning_roles()
        if not roles:
            await query.edit_message_text(
                "Нет ролей планирования. Обратитесь к администратору.",
                reply_markup=inline_back_cancel(CREATE_PREFIX, 1),
            )
            return
        await query.edit_message_text(
            "Выберите роль:",
            reply_markup=inline_list_with_nav(roles, CREATE_PREFIX, "role", 2),
        )
        return

    if parts[0] == "role" and len(parts) >= 2:
        state.data["role_id"] = int(parts[1])
        state.step = 4
        projects = odoo.get_projects()
        await query.edit_message_text(
            "Выберите проект:",
            reply_markup=inline_list_with_nav(
                projects if projects else [{"id": False, "name": "— Без проекта —"}],
                CREATE_PREFIX,
                "proj",
                3,
            ),
        )
        return

    if parts[0] == "proj" and len(parts) >= 2:
        try:
            state.data["project_id"] = int(parts[1])
        except ValueError:
            state.data["project_id"] = False
        state.step = 5
        await query.edit_message_text(
            f"Введите дату начала в формате {config.DATE_FORMAT_HINT} (время 08:00):",
            reply_markup=inline_back_cancel(CREATE_PREFIX, 4),
        )
        return


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    state,
    odoo: OdooClient,
) -> bool:
    """Handle text input for steps 5 (start_date), 6 (end_date), 7 (comment). Returns True if consumed."""
    text = (update.message.text or "").strip()
    if not text or text in ("Назад", "Отмена"):
        return False

    if state.step == 5:
        d = parse_date_ddmmyyyy(text)
        if not d:
            await update.message.reply_text(
                f"Неверный формат даты. Введите {config.DATE_FORMAT_HINT}.",
                reply_markup=inline_back_cancel(CREATE_PREFIX, 4),
            )
            return True
        state.data["start_date"] = d
        state.step = 6
        await update.message.reply_text(
            f"Введите дату окончания в формате {config.DATE_FORMAT_HINT} (время 17:00):",
            reply_markup=inline_back_cancel(CREATE_PREFIX, 5),
        )
        return True

    if state.step == 6:
        d = parse_date_ddmmyyyy(text)
        if not d:
            await update.message.reply_text(
                f"Неверный формат даты. Введите {config.DATE_FORMAT_HINT}.",
                reply_markup=inline_back_cancel(CREATE_PREFIX, 5),
            )
            return True
        if d < state.data["start_date"]:
            await update.message.reply_text(
                "Дата окончания не может быть раньше даты начала.",
                reply_markup=inline_back_cancel(CREATE_PREFIX, 5),
            )
            return True
        state.data["end_date"] = d
        state.step = 7
        await update.message.reply_text(
            "Введите комментарий (название слота):",
            reply_markup=inline_back_cancel(CREATE_PREFIX, 6),
        )
        return True

    if state.step == 7:
        state.data["name"] = text or "Слот"
        # Create slot
        tz = state.odoo_user_tz or "UTC"
        start_dt, end_dt = build_slot_start_end_utc(
            state.data["start_date"],
            state.data["end_date"],
            tz,
            config.DEFAULT_SLOT_START_TIME,
            config.DEFAULT_SLOT_END_TIME,
        )
        if not start_dt or not end_dt:
            await update.message.reply_text(
                "Ошибка при расчёте времени. Попробуйте снова.",
                reply_markup=inline_back_cancel(CREATE_PREFIX, 6),
            )
            return True
        vals = {
            "resource_id": state.data["resource_id"],
            "role_id": state.data["role_id"],
            "project_id": state.data.get("project_id") or False,
            "start_datetime": datetime_to_odoo_str(start_dt),
            "end_datetime": datetime_to_odoo_str(end_dt),
            "name": state.data["name"],
            "x_is_telegram_bot": True,
        }
        try:
            slot_id = odoo.slot_create(vals)
            chat_id = update.effective_chat.id
            state = get_state(chat_id)
            access_level = state.telegram_access_level
            clear_state(chat_id)
            await update.message.reply_text(
                f"Слот создан (ID: {slot_id}).",
                reply_markup=main_menu_keyboard(access_level),
            )
        except Exception as e:
            await update.message.reply_text(
                f"Ошибка при создании слота: {e}",
                reply_markup=back_cancel_keyboard(),
            )
        return True

    return False
