"""Proposed action persistence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from triage_db.audit import SYSTEM_ACTOR, action_event_type, record_event
from triage_db.jsonutil import dump_json, load_json, parse_ts


def save_action(
    conn: Connection, document: dict[str, Any], *, actor: Mapping[str, Any] | None = None
) -> None:
    decided_by = document.get("decided_by")
    execution_result = document.get("execution_result")
    conn.execute(
        text(
            """
            INSERT INTO actions (
                action_id, case_id, type, params, risk, status, proposed_by,
                decided_by, decided_at, execution_result, document
            ) VALUES (
                CAST(:action_id AS uuid), CAST(:case_id AS uuid), :type,
                CAST(:params AS jsonb), :risk, :status, CAST(:proposed_by AS jsonb),
                CAST(:decided_by AS jsonb), :decided_at, CAST(:execution_result AS jsonb),
                CAST(:document AS jsonb)
            )
            """
        ),
        {
            "action_id": document["action_id"],
            "case_id": document["case_id"],
            "type": document["type"],
            "params": dump_json(document["params"]),
            "risk": document["risk"],
            "status": document["status"],
            "proposed_by": dump_json(document["proposed_by"]),
            "decided_by": None if decided_by is None else dump_json(decided_by),
            "decided_at": parse_ts(document.get("decided_at")),
            "execution_result": None if execution_result is None else dump_json(execution_result),
            "document": dump_json(document),
        },
    )
    status = document["status"]
    who = dict(actor) if actor is not None else dict(SYSTEM_ACTOR)
    if status == "executing":
        return
    if status == "expired":
        record_event(
            conn,
            event_type="case.status_changed",
            actor=who,
            case_id=document["case_id"],
            data={
                "action_id": document["action_id"],
                "action_status": "expired",
                "reason": "action_expired",
            },
        )
        return
    record_event(
        conn,
        event_type=action_event_type(status),
        actor=who,
        case_id=document["case_id"],
        data={"action_id": document["action_id"], "status": status, "type": document["type"]},
    )


def get_action(conn: Connection, action_id: str) -> dict[str, Any]:
    document = conn.execute(
        text("SELECT document FROM actions WHERE action_id = CAST(:action_id AS uuid)"),
        {"action_id": action_id},
    ).scalar_one()
    return load_json(document)
