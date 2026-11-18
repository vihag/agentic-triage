"""Mock synchronous action executor for the console slice."""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import Connection
from triage_db.audit import SYSTEM_ACTOR
from triage_db.repositories.action_query import replace_action


def execute_approved_action(conn: Connection, action: dict[str, Any]) -> dict[str, Any]:
    executing = {**action, "status": "executing"}
    replace_action(conn, executing, actor=dict(SYSTEM_ACTOR))
    executed = {
        **executing,
        "status": "executed",
        "execution_result": {"ok": True, "executor": "mock"},
    }
    replace_action(conn, executed, actor=dict(SYSTEM_ACTOR))
    return executed