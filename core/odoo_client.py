# Part of atkinternal. See LICENSE file for full copyright and licensing details.

"""Odoo XML-RPC client for Planning and related models."""

import xmlrpc.client
from typing import Any, Optional

from .. import config


def _unique_by_id(rows: list) -> list:
    """Return list of dicts with unique 'id'; first occurrence kept."""
    seen = set()
    out = []
    for r in rows:
        rid = r.get("id")
        if rid is None or rid in seen:
            continue
        seen.add(rid)
        out.append(r)
    return out


class OdooClient:
    """Sync Odoo client via XML-RPC. Bot uses bot user; access check uses telegram_id."""

    def __init__(
        self,
        url: Optional[str] = None,
        db: Optional[str] = None,
        login: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.url = (url or config.ODOO_URL).rstrip("/")
        self.db = db or config.ODOO_DB
        self.login = login or config.ODOO_BOT_LOGIN
        self.password = password or config.ODOO_BOT_PASSWORD
        self._uid: Optional[int] = None
        self._common = None
        self._models = None

    def _get_common(self):
        if self._common is None:
            self._common = xmlrpc.client.ServerProxy(
                f"{self.url}/xmlrpc/2/common",
                allow_none=True,
            )
        return self._common

    def _get_models(self):
        if self._models is None:
            self._models = xmlrpc.client.ServerProxy(
                f"{self.url}/xmlrpc/2/object",
                allow_none=True,
            )
        return self._models

    def authenticate(self) -> Optional[int]:
        """Authenticate as bot user. Returns uid or None."""
        try:
            uid = self._get_common().authenticate(
                self.db, self.login, self.password, {}
            )
            if uid:
                self._uid = uid
                return uid
        except Exception:
            pass
        return None

    @property
    def uid(self) -> Optional[int]:
        if self._uid is None:
            self.authenticate()
        return self._uid

    def execute(
        self,
        model: str,
        method: str,
        args: list,
        kwargs: Optional[dict] = None,
    ) -> Any:
        """Execute model method as bot user."""
        if self.uid is None:
            raise RuntimeError("Odoo: not authenticated")
        return self._get_models().execute_kw(
            self.db,
            self.uid,
            self.password,
            model,
            method,
            args,
            kwargs or {},
        )

    def search_read(
        self,
        model: str,
        domain: list,
        fields: Optional[list] = None,
        limit: Optional[int] = None,
        order: Optional[str] = None,
    ) -> list:
        kwargs = {}
        if fields is not None:
            kwargs["fields"] = fields
        if limit is not None:
            kwargs["limit"] = limit
        if order is not None:
            kwargs["order"] = order
        return self.execute(model, "search_read", [domain], kwargs)

    # --- Access: find Odoo user by Telegram ID ---------------------------------

    def get_user_by_telegram_id(self, telegram_user_id: str) -> Optional[dict]:
        """Return res.users record (id, tz, ...) or None."""
        telegram_user_id = (telegram_user_id or "").strip()
        if not telegram_user_id:
            return None
        rows = self.search_read(
            "res.users",
            [("x_telegram_user_id", "=", telegram_user_id)],
            fields=["id", "name", "tz", "login", "x_telegram_access_level"],
            limit=1,
        )
        return rows[0] if rows else None

    # --- Planning: departments, employees, roles, projects ---------------------

    def get_departments(self) -> list:
        """List hr.department (id, name). Unique by id."""
        rows = self.search_read(
            "hr.department",
            [],
            fields=["id", "name"],
            order="name",
        )
        return _unique_by_id(rows)

    def get_employees_by_department(self, department_id: int) -> list:
        """Employees of department (hr.employee.department_id); id, name, resource_id."""
        rows = self.search_read(
            "hr.employee",
            [("department_id", "=", department_id)],
            fields=["id", "name", "resource_id"],
            order="name",
        )
        return _unique_by_id(rows)

    def get_planning_roles(self) -> list:
        """List planning.role (id, name)."""
        return self.search_read(
            "planning.role",
            [],
            fields=["id", "name"],
            order="name",
        )

    def get_projects(self) -> list:
        """List project.project (id, name)."""
        return self.search_read(
            "project.project",
            [],
            fields=["id", "name"],
            order="name",
        )

    # --- planning.slot: create, read, update, unlink --------------------------

    def slot_create(self, vals: dict) -> int:
        """Create planning.slot; vals must include x_is_telegram_bot=True."""
        return self.execute("planning.slot", "create", [vals])

    def slot_search_read(
        self,
        domain: list,
        fields: Optional[list] = None,
        limit: Optional[int] = None,
        order: Optional[str] = None,
    ) -> list:
        return self.search_read(
            "planning.slot",
            domain,
            fields=fields or [
                "id", "name", "resource_id", "role_id", "project_id",
                "start_datetime", "end_datetime", "x_is_telegram_bot",
            ],
            limit=limit,
            order=order,
        )

    def slot_write(self, slot_ids: list, vals: dict) -> bool:
        return self.execute("planning.slot", "write", [slot_ids, vals])

    def slot_unlink(self, slot_ids: list) -> bool:
        return self.execute("planning.slot", "unlink", [slot_ids])

    # --- Free resource: slots by resource and day, role "Для распределения" ----

    def get_role_by_name(self, name: str) -> Optional[dict]:
        """First planning.role with given name."""
        rows = self.search_read(
            "planning.role",
            [("name", "ilike", name)],
            fields=["id", "name"],
            limit=1,
        )
        return rows[0] if rows else None

    def get_project_by_name(self, name: str) -> Optional[dict]:
        """First project.project with given name (ilike)."""
        name = (name or "").strip()
        if not name:
            return None
        rows = self.search_read(
            "project.project",
            [("name", "ilike", name)],
            fields=["id", "name"],
            limit=1,
        )
        return rows[0] if rows else None

    def get_all_employees_with_resource(self) -> list:
        """Employees that have resource_id set (for planning)."""
        return self.search_read(
            "hr.employee",
            [("resource_id", "!=", False)],
            fields=["id", "name", "resource_id"],
            order="name",
        )
