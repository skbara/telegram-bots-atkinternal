# Part of atkinternal. See LICENSE file for full copyright and licensing details.

"""Conversation state for the bot (in-memory)."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

# In-memory store: chat_id -> UserState
_user_states: dict[int, "UserState"] = {}


class Scenario(str, Enum):
    NONE = "none"
    CREATE_SLOT = "create_slot"
    EDIT_SLOT = "edit_slot"
    FREE_RESOURCE = "free_resource"


@dataclass
class UserState:
    """State for one user (chat)."""

    odoo_user_id: Optional[int] = None
    odoo_user_tz: Optional[str] = None
    scenario: Scenario = Scenario.NONE
    step: int = 0
    data: dict[str, Any] = field(default_factory=dict)
    last_message_id: Optional[int] = None

    def clear(self):
        self.scenario = Scenario.NONE
        self.step = 0
        self.data.clear()
        self.last_message_id = None


def get_state(chat_id: int) -> UserState:
    if chat_id not in _user_states:
        _user_states[chat_id] = UserState()
    return _user_states[chat_id]


def clear_state(chat_id: int):
    if chat_id in _user_states:
        _user_states[chat_id].clear()
