# Part of atkinternal. See LICENSE file for full copyright and licensing details.

"""Scenario 2: Edit or delete planning.slot (only x_is_telegram_bot=True)."""

from datetime import datetime

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from .. import config
from ..core import OdooClient, get_state, clear_state, Scenario
from ..keyboards import (
    BTN_BACK,
    BTN_CANCEL,
    inline_list,
    inline_list_with_nav,
    inline_back_cancel,
    back_cancel_keyboard,
    main_menu_keyboard,
)
from ..utils import (
    parse_date_ddmmyyyy,
    build_slot_start_end_utc,
    datetime_to_odoo_str,
)
from .menu import WELCOME


EDIT_PREFIX = "edit"


def setup_edit_slot_handlers(app, odoo: OdooClient):
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, odoo: OdooClient):
    """Start edit flow: choose department."""
    state = get_state(update.effective_chat.id)
    state.scenario = Scenario.EDIT_SLOT
    state.step = 1
    state.data = {}
    depts = odoo.get_departments()
    if not depts:
        await update.message.reply_text(
            "Нет отделов.",
            reply_markup=back_cancel_keyboard(),
        )
        return
    # На первом шаге редактирования возвращаться «Назад» некуда,
    # поэтому показываем только список отделов и кнопку «Отмена».
    base_kb = inline_list(depts, f"{EDIT_PREFIX}_dept")
    rows = list(base_kb.inline_keyboard)
    rows.append(
        [InlineKeyboardButton(BTN_CANCEL, callback_data=f"{EDIT_PREFIX}_cancel")]
    )
    await update.message.reply_text(
        "Выберите отдел:",
        reply_markup=InlineKeyboardMarkup(rows),
    )


def _slot_domain_for_period(resource_id: int, start_dt, end_dt) -> list:
    """Domain: resource, bot slot, overlaps [start_dt, end_dt]."""
    return [
        ("resource_id", "=", resource_id),
        ("x_is_telegram_bot", "=", True),
        ("start_datetime", "<", datetime_to_odoo_str(end_dt)),
        ("end_datetime", ">", datetime_to_odoo_str(start_dt)),
    ]


def _format_slot_items(slots: list) -> list[dict]:
    """Build display labels for slots: DD/MM - DD/MM - role - project."""
    items: list[dict] = []
    for s in slots:
        start_raw = s.get("start_datetime")
        end_raw = s.get("end_datetime")
        try:
            start_dt = (
                datetime.fromisoformat(start_raw)
                if isinstance(start_raw, str)
                else start_raw
            )
            end_dt = (
                datetime.fromisoformat(end_raw)
                if isinstance(end_raw, str)
                else end_raw
            )
        except Exception:
            start_dt = end_dt = None
        if start_dt and end_dt:
            start_str = start_dt.strftime("%d/%m")
            end_str = end_dt.strftime("%d/%m")
        else:
            start_str = str(start_raw)[:10]
            end_str = str(end_raw)[:10]
        role = s.get("role_id") or []
        proj = s.get("project_id") or []
        role_name = role[1] if isinstance(role, (list, tuple)) and len(role) > 1 else "-"
        proj_name = proj[1] if isinstance(proj, (list, tuple)) and len(proj) > 1 else "-"
        label = f"{start_str} - {end_str} - {role_name} - {proj_name}"
        items.append({"id": s["id"], "name": label})
    return items


def _push_edit_history(state, prev_step: int):
    """Добавить предыдущий шаг в историю редактирования."""
    hist = state.data.get("edit_history") or []
    hist.append(prev_step)
    state.data["edit_history"] = hist


def _pop_edit_history(state):
    """Извлечь предыдущий шаг из истории редактирования."""
    hist = state.data.get("edit_history") or []
    if not hist:
        return None
    prev = hist.pop()
    state.data["edit_history"] = hist
    return prev


async def handle_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    odoo: OdooClient,
    parts: list,
):
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
        # Для шагов редактирования (>=8) «Назад» ведёт на фактически
        # предыдущий посещённый шаг, который хранится в edit_history.
        if step_back >= 8:
            prev = _pop_edit_history(state)
            if prev is not None:
                step_back = prev
            else:
                # Если истории нет, считаем предыдущим шагом список изменений.
                step_back = 8
        state.step = step_back
        if step_back == 0:
            clear_state(chat_id)
            await query.edit_message_text(
                WELCOME,
                reply_markup=InlineKeyboardMarkup([]),
            )
            return
        # Переходы "Назад" по шагам сценария редактирования
        if step_back == 1:
            # Вернуться к начальному шагу (выбор отдела, только «Отмена»)
            depts = odoo.get_departments()
            base_kb = inline_list(depts, f"{EDIT_PREFIX}_dept")
            rows = list(base_kb.inline_keyboard)
            rows.append(
                [
                    InlineKeyboardButton(
                        BTN_CANCEL, callback_data=f"{EDIT_PREFIX}_cancel"
                    )
                ]
            )
            await query.edit_message_text(
                "Выберите отдел:",
                reply_markup=InlineKeyboardMarkup(rows),
            )
            return
        if step_back == 2:
            # Вернуться к выбору сотрудника в ранее выбранном отделе
            department_id = state.data.get("department_id")
            if not department_id:
                depts = odoo.get_departments()
                await query.edit_message_text(
                    "Выберите отдел:",
                    reply_markup=inline_list_with_nav(depts, EDIT_PREFIX, "dept", 1),
                )
                state.step = 1
                return
            employees = odoo.get_employees_by_department(department_id)
            await query.edit_message_text(
                "Выберите сотрудника:",
                # На шаге выбора сотрудника кнопка «Назад» должна вести к отделам
                reply_markup=inline_list_with_nav(employees, EDIT_PREFIX, "emp", 1),
            )
            return
        if step_back == 3:
            # Вернуться к вводу даты начала периода
            await query.edit_message_text(
                f"Введите дату начала периода ({config.DATE_FORMAT_HINT}):",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 2),
            )
            return
        if step_back == 4:
            # Вернуться к вводу даты окончания периода
            await query.edit_message_text(
                f"Введите дату окончания периода ({config.DATE_FORMAT_HINT}):",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 3),
            )
            return
        # 8–16: шаги после выбора конкретного слота (multi-edit)
        if step_back == 8:
            # Вернуться к выбору изменений для слота
            state.step = 8
            state.data.setdefault("pending_edits", [])
            await query.edit_message_text(
                "Выберите нужные пункты и нажмите кнопку \"Готово\":\n"
                "• Поменять сотрудника\n"
                "• Изменить роль\n"
                "• Изменить проект\n"
                "• Изменить дату начала\n"
                "• Изменить дату окончания\n"
                "• Изменить комментарий\n"
                "• Удалить запись",
                reply_markup=_edit_actions_keyboard(state.data["pending_edits"]),
            )
            return
        if step_back == 9:
            # Вернуться к выбору отдела нового сотрудника
            depts = odoo.get_departments()
            if not depts:
                await query.edit_message_text(
                    "Нет отделов. Обратитесь к администратору.",
                    reply_markup=inline_back_cancel(EDIT_PREFIX, 8),
                )
                return
            state.step = 9
            await query.edit_message_text(
                "Выберите отдел нового сотрудника:",
                reply_markup=inline_list_with_nav(depts, EDIT_PREFIX, "dept2", 8),
            )
            return
        if step_back == 10:
            # Вернуться к выбору нового сотрудника в ранее выбранном отделе
            new_department_id = state.data.get("new_department_id")
            if not new_department_id:
                # Если отдел ещё не выбран — вернуться к его выбору
                depts = odoo.get_departments()
                state.step = 9
                await query.edit_message_text(
                    "Выберите отдел нового сотрудника:",
                    reply_markup=inline_list_with_nav(depts, EDIT_PREFIX, "dept2", 8),
                )
                return
            employees = odoo.get_employees_by_department(new_department_id)
            state.step = 10
            await query.edit_message_text(
                "Выберите нового сотрудника:",
                reply_markup=inline_list_with_nav(employees, EDIT_PREFIX, "emp2", 9),
            )
            return
        if step_back == 11:
            # Вернуться к выбору новой роли
            roles = odoo.get_planning_roles()
            state.step = 11
            await query.edit_message_text(
                "Выберите новую роль:",
                reply_markup=inline_list_with_nav(roles, EDIT_PREFIX, "role2", 10),
            )
            return
        if step_back == 12:
            # Вернуться к выбору нового проекта
            projects = odoo.get_projects()
            state.step = 12
            await query.edit_message_text(
                "Выберите новый проект:",
                reply_markup=inline_list_with_nav(
                    projects if projects else [{"id": False, "name": "— Без проекта —"}],
                    EDIT_PREFIX,
                    "proj2",
                    11,
                ),
            )
            return
        if step_back == 13:
            # Вернуться к вводу новой даты начала периода
            state.step = 13
            back_step = state.data.get("dates_back_step", 8)
            await query.edit_message_text(
                f"Введите новую дату начала периода ({config.DATE_FORMAT_HINT}):",
                reply_markup=inline_back_cancel(EDIT_PREFIX, back_step),
            )
            return
        if step_back == 14:
            # Вернуться к вводу новой даты окончания периода
            state.step = 14
            back_step = state.data.get("dates_back_step", 8)
            await query.edit_message_text(
                f"Введите новую дату окончания периода ({config.DATE_FORMAT_HINT}):",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 13),
            )
            return
        if step_back == 15:
            # Вернуться к вводу нового комментария
            state.step = 15
            back_step = state.data.get("comment_back_step", 8)
            await query.edit_message_text(
                "Введите новый комментарий:",
                reply_markup=inline_back_cancel(EDIT_PREFIX, back_step),
            )
            return
        if step_back == 16:
            # Вернуться к финальному подтверждению изменений
            await _show_confirm(update, state)
            return
        return

    if parts[0] == "dept" and len(parts) >= 2:
        state.data["department_id"] = int(parts[1])
        state.step = 2
        employees = odoo.get_employees_by_department(state.data["department_id"])
        if not employees:
            await query.edit_message_text(
                "В отделе нет сотрудников.",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 1),
            )
            return
        await query.edit_message_text(
            "Выберите сотрудника:",
            # На шаге выбора сотрудника «Назад» ведёт к выбору отдела (step_back=1)
            reply_markup=inline_list_with_nav(employees, EDIT_PREFIX, "emp", 1),
        )
        return

    if parts[0] == "emp" and len(parts) >= 2:
        state.data["employee_id"] = int(parts[1])
        emps = odoo.get_employees_by_department(state.data["department_id"])
        emp = next((e for e in emps if e["id"] == state.data["employee_id"]), None)
        if emp and emp.get("resource_id"):
            state.data["resource_id"] = emp["resource_id"][0]
        state.step = 3
        await query.edit_message_text(
            f"Введите дату начала периода ({config.DATE_FORMAT_HINT}):",
            reply_markup=inline_back_cancel(EDIT_PREFIX, 2),
        )
        return

    if parts[0] == "slot" and len(parts) >= 2:
        state.data["slot_id"] = int(parts[1])
        state.step = 8
        state.data.setdefault("pending_edits", [])
        await query.edit_message_text(
            "Выберите нужные пункты и нажмите кнопку \"Готово\":\n"
            "• Поменять сотрудника\n"
            "• Изменить роль\n"
            "• Изменить проект\n"
            "• Изменить дату начала\n"
            "• Изменить дату окончания\n"
            "• Изменить комментарий\n"
            "• Удалить запись",
            reply_markup=_edit_actions_keyboard(state.data["pending_edits"]),
        )
        return

    if parts[0] == "action" and len(parts) >= 2:
        action = parts[1]
        if action == "back":
            # Вернуться к выбору слота (шаг 5)
            state.step = 5
            tz = state.odoo_user_tz or "UTC"
            start_dt, end_dt = build_slot_start_end_utc(
                state.data["period_start_date"],
                state.data["period_end_date"],
                tz,
                config.DEFAULT_SLOT_START_TIME,
                config.DEFAULT_SLOT_END_TIME,
            )
            domain = _slot_domain_for_period(
                state.data["resource_id"],
                start_dt,
                end_dt,
            )
            slots = odoo.slot_search_read(domain, limit=20)
            if not slots:
                await query.edit_message_text(
                    "Нет слотов бота в выбранном периоде.",
                    reply_markup=inline_back_cancel(EDIT_PREFIX, 4),
                )
                return
            slot_items = _format_slot_items(slots)
            await query.edit_message_text(
                "Выберите слот:",
                reply_markup=inline_list_with_nav(
                    slot_items, EDIT_PREFIX, "slot", 4
                ),
            )
            return
        if action == "apply":
            await _apply_edits(update, context, state, odoo)
            return
        if action == "delete":
            # Тоггл режима удаления: если уже выбрано — убираем,
            # если нет — выбираем только удаление, сбрасывая остальные.
            pending = state.data.get("pending_edits") or []
            if "delete" in pending:
                pending = []
            else:
                pending = ["delete"]
            state.data["pending_edits"] = pending
        else:
            # Add to pending: emp, role, project, start, end, comment
            state.data.setdefault("pending_edits", [])
            # Если ранее было выбрано удаление — сбрасываем его.
            if "delete" in state.data["pending_edits"]:
                state.data["pending_edits"] = []
            if action in state.data["pending_edits"]:
                # Повторный выбор снимает галочку
                state.data["pending_edits"].remove(action)
            else:
                state.data["pending_edits"].append(action)
        await query.edit_message_text(
            "Выберите нужные пункты и нажмите кнопку \"Готово\":",
            reply_markup=_edit_actions_keyboard(state.data.get("pending_edits") or []),
        )
        return

    # --- Value selection for edits (after "Готово") ---------------------------

    if parts[0] == "dept2" and len(parts) >= 2:
        # Новый отдел для изменения сотрудника
        state.data["new_department_id"] = int(parts[1])
        _push_edit_history(state, 9)
        state.step = 10
        employees = odoo.get_employees_by_department(state.data["new_department_id"])
        if not employees:
            await query.edit_message_text(
                "В отделе нет сотрудников с ресурсом для планирования.",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 9),
            )
            return
        await query.edit_message_text(
            "Выберите нового сотрудника:",
            reply_markup=inline_list_with_nav(employees, EDIT_PREFIX, "emp2", 9),
        )
        return

    if parts[0] == "emp2" and len(parts) >= 2:
        # Новый сотрудник (ресурс) для слота
        state.data["new_employee_id"] = int(parts[1])
        emps = odoo.get_employees_by_department(state.data.get("new_department_id"))
        emp = next((e for e in emps if e["id"] == state.data["new_employee_id"]), None)
        if emp and emp.get("resource_id"):
            state.data["new_resource_id"] = emp["resource_id"][0]
        pending = state.data.get("pending_edits") or []
        # После выбора сотрудника переходим к следующему выбранному этапу
        if "role" in pending:
            roles = odoo.get_planning_roles()
            if not roles:
                await query.edit_message_text(
                    "Нет ролей планирования. Обратитесь к администратору.",
                    reply_markup=inline_back_cancel(EDIT_PREFIX, 9),
                )
                return
            _push_edit_history(state, 10)
            state.step = 11
            back_step = 10
            await query.edit_message_text(
                "Выберите новую роль:",
                reply_markup=inline_list_with_nav(
                    roles,
                    EDIT_PREFIX,
                    "role2",
                    back_step,
                ),
            )
            return
        if "project" in pending:
            projects = odoo.get_projects()
            _push_edit_history(state, 10)
            state.step = 12
            back_step = 10
            await query.edit_message_text(
                "Выберите новый проект:",
                reply_markup=inline_list_with_nav(
                    projects if projects else [{"id": False, "name": "— Без проекта —"}],
                    EDIT_PREFIX,
                    "proj2",
                    back_step,
                ),
            )
            return
        if "start" in pending and "end" in pending:
            _push_edit_history(state, 10)
            state.step = 13
            await query.edit_message_text(
                f"Введите новую дату начала периода ({config.DATE_FORMAT_HINT}):",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 10),
            )
            return
        if "start" in pending and "end" not in pending:
            _push_edit_history(state, 10)
            state.step = 13
            await query.edit_message_text(
                f"Введите новую дату начала периода ({config.DATE_FORMAT_HINT}):",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 10),
            )
            return
        if "end" in pending and "start" not in pending:
            _push_edit_history(state, 10)
            state.step = 14
            await query.edit_message_text(
                f"Введите новую дату окончания периода ({config.DATE_FORMAT_HINT}):",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 10),
            )
            return
        if "comment" in pending:
            _push_edit_history(state, 10)
            state.step = 15
            await query.edit_message_text(
                "Введите новый комментарий:",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 10),
            )
            return
        # Если больше нет этапов — сразу к подтверждению
        await _show_confirm(update, state)
        return

    if parts[0] == "role2" and len(parts) >= 2:
        state.data["new_role_id"] = int(parts[1])
        pending = state.data.get("pending_edits") or []
        if "project" in pending:
            projects = odoo.get_projects()
            _push_edit_history(state, 11)
            state.step = 12
            back_step = 11
            await query.edit_message_text(
                "Выберите новый проект:",
                reply_markup=inline_list_with_nav(
                    projects if projects else [{"id": False, "name": "— Без проекта —"}],
                    EDIT_PREFIX,
                    "proj2",
                    back_step,
                ),
            )
            return
        if "start" in pending and "end" in pending:
            _push_edit_history(state, 11)
            state.step = 13
            back_step = 11
            await query.edit_message_text(
                f"Введите новую дату начала периода ({config.DATE_FORMAT_HINT}):",
                reply_markup=inline_back_cancel(EDIT_PREFIX, back_step),
            )
            return
        if "start" in pending and "end" not in pending:
            _push_edit_history(state, 11)
            state.step = 13
            back_step = 11
            await query.edit_message_text(
                f"Введите новую дату начала периода ({config.DATE_FORMAT_HINT}):",
                reply_markup=inline_back_cancel(EDIT_PREFIX, back_step),
            )
            return
        if "end" in pending and "start" not in pending:
            _push_edit_history(state, 11)
            state.step = 14
            back_step = 11
            await query.edit_message_text(
                f"Введите новую дату окончания периода ({config.DATE_FORMAT_HINT}):",
                reply_markup=inline_back_cancel(EDIT_PREFIX, back_step),
            )
            return
        if "comment" in pending:
            _push_edit_history(state, 11)
            state.step = 15
            await query.edit_message_text(
                "Введите новый комментарий:",
                reply_markup=inline_back_cancel(EDIT_PREFIX, back_step),
            )
            return
        await _show_confirm(update, state)
        return

    if parts[0] == "proj2" and len(parts) >= 2:
        try:
            state.data["new_project_id"] = int(parts[1])
        except ValueError:
            state.data["new_project_id"] = False
        pending = state.data.get("pending_edits") or []
        if "start" in pending and "end" in pending:
            _push_edit_history(state, 12)
            state.step = 13
            back_step = 12
            await query.edit_message_text(
                f"Введите новую дату начала периода ({config.DATE_FORMAT_HINT}):",
                reply_markup=inline_back_cancel(EDIT_PREFIX, back_step),
            )
            return
        if "start" in pending and "end" not in pending:
            _push_edit_history(state, 12)
            state.step = 13
            back_step = 12
            await query.edit_message_text(
                f"Введите новую дату начала периода ({config.DATE_FORMAT_HINT}):",
                reply_markup=inline_back_cancel(EDIT_PREFIX, back_step),
            )
            return
        if "end" in pending and "start" not in pending:
            _push_edit_history(state, 12)
            state.step = 14
            back_step = 12
            await query.edit_message_text(
                f"Введите новую дату окончания периода ({config.DATE_FORMAT_HINT}):",
                reply_markup=inline_back_cancel(EDIT_PREFIX, back_step),
            )
            return
        if "comment" in pending:
            _push_edit_history(state, 12)
            state.step = 15
            back_step = 12
            await query.edit_message_text(
                "Введите новый комментарий:",
                reply_markup=inline_back_cancel(EDIT_PREFIX, back_step),
            )
            return
        await _show_confirm(update, state)
        return

    if parts[0] == "commit" and len(parts) >= 2:
        action = parts[1]
        if action == "send":
            await _commit_edits(update, context, state, odoo)
            return
        if action == "back":
            pending = state.data.get("pending_edits") or []
            # Определяем, к какому шагу вернуться перед подтверждением
            if "comment" in pending:
                target_step = 15
            elif "start" in pending or "end" in pending:
                target_step = 14
            elif "project" in pending:
                target_step = 12
            elif "role" in pending:
                target_step = 11
            elif "emp" in pending:
                target_step = 10
            else:
                target_step = 8
            # Эмулируем нажатие кнопки "Назад" к нужному шагу
            fake_parts = ["back", str(target_step)]
            await handle_callback(update, context, odoo, fake_parts)
            return
        return


def _edit_actions_keyboard(pending: list[str]):
    """Inline keyboard for multi-select edit actions with checkmarks."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    def _label(key: str, title: str) -> str:
        # Используем компактный стиль: добавляем " ✓" только к выбранным пунктам.
        return f"{title} ✓" if key in pending else title

    rows = [
        [
            InlineKeyboardButton(
                _label("emp", "Сотрудник"),
                callback_data="edit_action:emp",
            )
        ],
        [
            InlineKeyboardButton(
                _label("role", "Роль"),
                callback_data="edit_action:role",
            )
        ],
        [
            InlineKeyboardButton(
                _label("project", "Проект"),
                callback_data="edit_action:project",
            )
        ],
        [
            InlineKeyboardButton(
                _label("start", "Дата начала"),
                callback_data="edit_action:start",
            )
        ],
        [
            InlineKeyboardButton(
                _label("end", "Дата окончания"),
                callback_data="edit_action:end",
            )
        ],
        [
            InlineKeyboardButton(
                _label("comment", "Комментарий"),
                callback_data="edit_action:comment",
            )
        ],
        [
            InlineKeyboardButton(
                _label("delete", "Удалить слот"),
                callback_data="edit_action:delete",
            )
        ],
        [InlineKeyboardButton("Готово", callback_data="edit_action:apply")],
        [
            InlineKeyboardButton("Назад", callback_data="edit_action:back"),
            InlineKeyboardButton(BTN_CANCEL, callback_data="edit_cancel"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


async def _apply_edits(update: Update, context, state, odoo: OdooClient):
    query = update.callback_query
    pending = state.data.get("pending_edits") or []
    slot_id = state.data.get("slot_id")
    if not slot_id:
        await query.edit_message_text("Ошибка: слот не выбран.")
        clear_state(update.effective_chat.id)
        return
    if "delete" in pending and len(pending) == 1:
        try:
            odoo.slot_unlink([slot_id])
            clear_state(update.effective_chat.id)
            await query.edit_message_text(
                "Слот удалён.",
                reply_markup=InlineKeyboardMarkup([]),
            )
        except Exception as e:
            await query.edit_message_text(f"Ошибка удаления: {e}")
        return
    if not pending:
        await query.answer("Не выбрано ни одного изменения.")
        return
    # Для остальных изменений запускаем пошаговый сценарий ввода новых значений.
    state.data["pending_edits"] = pending
    # Инициализируем историю переходов внутри сценария редактирования.
    state.data["edit_history"] = []
    # Загружаем текущие значения слота (может пригодиться для будущего расширения/валидации).
    slot_rows = odoo.slot_search_read([("id", "=", slot_id)], limit=1)
    if slot_rows:
        state.data["current_slot"] = slot_rows[0]
    pending_set = set(pending)
    # Определяем первую форму ввода по приоритету: сотрудник → роль → проект → даты → комментарий.
    if "emp" in pending_set:
        depts = odoo.get_departments()
        if not depts:
            await query.edit_message_text(
                "Нет отделов. Обратитесь к администратору.",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 8),
            )
            return
        _push_edit_history(state, 8)
        state.step = 9
        await query.edit_message_text(
            "Выберите отдел нового сотрудника:",
            reply_markup=inline_list_with_nav(depts, EDIT_PREFIX, "dept2", 8),
        )
        return
    if "role" in pending_set:
        roles = odoo.get_planning_roles()
        if not roles:
            await query.edit_message_text(
                "Нет ролей планирования. Обратитесь к администратору.",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 8),
            )
            return
        _push_edit_history(state, 8)
        state.step = 11
        await query.edit_message_text(
            "Выберите новую роль:",
            reply_markup=inline_list_with_nav(roles, EDIT_PREFIX, "role2", 8),
        )
        return
    if "project" in pending_set:
        projects = odoo.get_projects()
        _push_edit_history(state, 8)
        state.step = 12
        await query.edit_message_text(
            "Выберите новый проект:",
            reply_markup=inline_list_with_nav(
                projects if projects else [{"id": False, "name": "— Без проекта —"}],
                EDIT_PREFIX,
                "proj2",
                8,
            ),
        )
        return
    if "start" in pending_set and "end" in pending_set:
        # Меняем обе даты: сначала спрашиваем новую дату начала, затем окончания.
        _push_edit_history(state, 8)
        state.step = 13
        await query.edit_message_text(
            f"Введите новую дату начала периода ({config.DATE_FORMAT_HINT}):",
            reply_markup=inline_back_cancel(EDIT_PREFIX, 8),
        )
        return
    if "start" in pending_set and "end" not in pending_set:
        # Меняем только дату начала.
        _push_edit_history(state, 8)
        state.step = 13
        await query.edit_message_text(
            f"Введите новую дату начала периода ({config.DATE_FORMAT_HINT}):",
            reply_markup=inline_back_cancel(EDIT_PREFIX, 8),
        )
        return
    if "end" in pending_set and "start" not in pending_set:
        # Меняем только дату окончания.
        _push_edit_history(state, 8)
        state.step = 14
        await query.edit_message_text(
            f"Введите новую дату окончания периода ({config.DATE_FORMAT_HINT}):",
            reply_markup=inline_back_cancel(EDIT_PREFIX, 8),
        )
        return
    # Остаётся только комментарий
    _push_edit_history(state, 8)
    state.step = 15
    await query.edit_message_text(
        "Введите новый комментарий:",
        reply_markup=inline_back_cancel(EDIT_PREFIX, 8),
    )


async def _commit_edits(
    update: Update,
    context,
    state,
    odoo: OdooClient,
):
    """Отправить накопленные изменения слота в Odoo."""
    query = update.callback_query
    pending = state.data.get("pending_edits") or []
    slot_id = state.data.get("slot_id")
    if not slot_id:
        await query.edit_message_text("Ошибка: слот не выбран.")
        clear_state(update.effective_chat.id)
        return
    vals: dict = {}
    if "emp" in pending:
        new_resource_id = state.data.get("new_resource_id")
        if not new_resource_id:
            await query.edit_message_text(
                "Не выбран новый сотрудник для слота.",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 9),
            )
            return
        vals["resource_id"] = new_resource_id
    if "role" in pending:
        new_role_id = state.data.get("new_role_id")
        if not new_role_id:
            await query.edit_message_text(
                "Не выбрана новая роль.",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 11),
            )
            return
        vals["role_id"] = new_role_id
    if "project" in pending:
        vals["project_id"] = state.data.get("new_project_id") or False
    if "start" in pending or "end" in pending:
        current_slot = state.data.get("current_slot") or {}
        start_raw = current_slot.get("start_datetime")
        end_raw = current_slot.get("end_datetime")
        from datetime import datetime as _dt
        try:
            cur_start_dt = _dt.fromisoformat(start_raw) if isinstance(start_raw, str) else None
        except Exception:
            cur_start_dt = None
        try:
            cur_end_dt = _dt.fromisoformat(end_raw) if isinstance(end_raw, str) else None
        except Exception:
            cur_end_dt = None
        new_start_date = state.data.get("new_start_date")
        new_end_date = state.data.get("new_end_date")
        # Строим новые значения, подставляя только те даты, которые реально менялись.
        if "start" in pending:
            if not (new_start_date and cur_start_dt):
                await query.edit_message_text(
                    "Не удалось определить новое значение даты начала.",
                    reply_markup=inline_back_cancel(EDIT_PREFIX, 13),
                )
                return
            cur_start_dt = cur_start_dt.replace(
                year=new_start_date.year,
                month=new_start_date.month,
                day=new_start_date.day,
            )
        if "end" in pending:
            if not (new_end_date and cur_end_dt):
                await query.edit_message_text(
                    "Не удалось определить новое значение даты окончания.",
                    reply_markup=inline_back_cancel(EDIT_PREFIX, 13),
                )
                return
            cur_end_dt = cur_end_dt.replace(
                year=new_end_date.year,
                month=new_end_date.month,
                day=new_end_date.day,
            )
        # Финальная проверка: конец не раньше начала.
        if cur_start_dt and cur_end_dt and cur_end_dt < cur_start_dt:
            await query.edit_message_text(
                "Дата окончания не может быть раньше даты начала.",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 13),
            )
            return
        if cur_start_dt:
            vals["start_datetime"] = datetime_to_odoo_str(cur_start_dt)
        if cur_end_dt:
            vals["end_datetime"] = datetime_to_odoo_str(cur_end_dt)
    if "comment" in pending:
        new_comment = state.data.get("new_comment")
        if new_comment is None:
            await query.edit_message_text(
                "Не задан новый комментарий.",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 15),
            )
            return
        vals["name"] = new_comment
    if not vals:
        await query.answer("Нет изменений для применения.")
        return
    try:
        odoo.slot_write([slot_id], vals)
        clear_state(update.effective_chat.id)
        await query.edit_message_text(
            "Изменения успешно применены к слоту.",
            reply_markup=InlineKeyboardMarkup([]),
        )
    except Exception as exc:
        await query.edit_message_text(
            f"Ошибка при применении изменений: {exc}",
            reply_markup=inline_back_cancel(EDIT_PREFIX, 8),
        )


async def _show_confirm(update: Update, state):
    """Показать финальное окно подтверждения изменений."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Отправить изменения",
                    callback_data="edit_commit:send",
                )
            ],
            [
                InlineKeyboardButton(
                    "Назад",
                    callback_data="edit_commit:back",
                ),
                InlineKeyboardButton(
                    BTN_CANCEL,
                    callback_data="edit_cancel",
                ),
            ],
        ]
    )
    _push_edit_history(state, state.step)
    state.step = 16
    # Может вызываться как из callback (inline-кнопка), так и из текстового сообщения.
    if update.callback_query:
        query = update.callback_query
        await query.edit_message_text(
            "Проверьте изменения и нажмите «Отправить изменения» для применения.",
            reply_markup=kb,
        )
    elif update.message:
        await update.message.reply_text(
            "Проверьте изменения и нажмите «Отправить изменения» для применения.",
            reply_markup=kb,
        )


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    state,
    odoo: OdooClient,
) -> bool:
    """Steps:
    3→4: start_date периода, 4→5: end_date периода (поиск слотов);
    13→14: новые даты слота, 15: новый комментарий, затем подтверждение."""
    text = (update.message.text or "").strip()
    if not text or text in ("Назад", "Отмена"):
        return False

    if state.step == 3:
        d = parse_date_ddmmyyyy(text)
        if not d:
            await update.message.reply_text(
                f"Неверный формат. Введите {config.DATE_FORMAT_HINT}.",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 2),
            )
            return True
        state.data["period_start_date"] = d
        state.step = 4
        await update.message.reply_text(
            f"Введите дату окончания периода ({config.DATE_FORMAT_HINT}):",
            reply_markup=inline_back_cancel(EDIT_PREFIX, 3),
        )
        return True

    if state.step == 4:
        d = parse_date_ddmmyyyy(text)
        if not d:
            await update.message.reply_text(
                f"Неверный формат. Введите {config.DATE_FORMAT_HINT}.",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 3),
            )
            return True
        if d < state.data["period_start_date"]:
            await update.message.reply_text(
                "Дата окончания не может быть раньше начала периода.",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 3),
            )
            return True
        state.data["period_end_date"] = d
        tz = state.odoo_user_tz or "UTC"
        start_dt, end_dt = build_slot_start_end_utc(
            state.data["period_start_date"],
            d,
            tz,
            config.DEFAULT_SLOT_START_TIME,
            config.DEFAULT_SLOT_END_TIME,
        )
        if not start_dt or not end_dt:
            await update.message.reply_text("Ошибка расчёта периода.", reply_markup=back_cancel_keyboard())
            return True
        domain = _slot_domain_for_period(
            state.data["resource_id"],
            start_dt,
            end_dt,
        )
        slots = odoo.slot_search_read(domain, limit=20)
        if not slots:
            # Нет слотов в периоде: даём возможность вернуться к вводу
            # даты окончания периода через inline-кнопку «Назад».
            await update.message.reply_text(
                "Нет слотов бота в выбранном периоде.",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 4),
            )
            return True
        state.step = 5
        slot_items = _format_slot_items(slots)
        await update.message.reply_text(
            "Выберите слот:",
            reply_markup=inline_list_with_nav(slot_items, EDIT_PREFIX, "slot", 4),
        )
        return True

    # Новые значения для выбранного слота

    if state.step == 13:
        # Ввод новой даты начала слота
        d = parse_date_ddmmyyyy(text)
        if not d:
            await update.message.reply_text(
                f"Неверный формат. Введите {config.DATE_FORMAT_HINT}.",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 13),
            )
            return True
        state.data["new_start_date"] = d
        pending = state.data.get("pending_edits") or []
        # Если нужно менять и дату окончания — переходим к шагу 14.
        if "end" in pending:
            _push_edit_history(state, 13)
            state.step = 14
            await update.message.reply_text(
                f"Введите новую дату окончания периода ({config.DATE_FORMAT_HINT}):",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 13),
            )
            return True
        # Если дата окончания не выбрана для изменения:
        # либо идём к комментарию, либо сразу к подтверждению.
        if "comment" in pending:
            _push_edit_history(state, 13)
            state.step = 15
            await update.message.reply_text(
                "Введите новый комментарий:",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 13),
            )
            return True
        await _show_confirm(update, state)
        return True

    if state.step == 14:
        # Ввод новой даты окончания слота
        d = parse_date_ddmmyyyy(text)
        if not d:
            await update.message.reply_text(
                f"Неверный формат. Введите {config.DATE_FORMAT_HINT}.",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 13),
            )
            return True
        # Для валидации используем новую дату начала (если есть)
        # или текущую дату начала слота из Odoo.
        new_start = state.data.get("new_start_date")
        if not new_start:
            current_slot = state.data.get("current_slot") or {}
            start_raw = current_slot.get("start_datetime")
            if isinstance(start_raw, str):
                try:
                    from datetime import datetime as _dt
                    new_start = _dt.fromisoformat(start_raw).date()
                except Exception:
                    new_start = None
        if new_start and d < new_start:
            await update.message.reply_text(
                "Дата окончания не может быть раньше даты начала.",
                reply_markup=inline_back_cancel(EDIT_PREFIX, 13),
            )
            return True
        state.data["new_end_date"] = d
        pending = state.data.get("pending_edits") or []
        if "comment" in pending:
            # Переходим к вводу комментария
            _push_edit_history(state, 14)
            state.step = 15
            await update.message.reply_text(
                "Введите новый комментарий:",
                reply_markup=inline_back_cancel(
                    EDIT_PREFIX,
                    14,
                ),
            )
            return True
        # Если комментарий не выбран — сразу к подтверждению
        await _show_confirm(update, state)
        return True

    if state.step == 15:
        # Ввод нового комментария слота
        state.data["new_comment"] = text
        await _show_confirm(update, state)
        return True

    return False
