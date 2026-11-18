"""Action reads and updates."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from triage_db.audit import action_event_type, record_event
from triage_db.jsonutil import dump_json, load_json, parse_ts


def list_actions_for_case(conn: Connection, case_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            SELECT document FROM actions
            WHERE case_id = CAST(:case_id AS uuid)
            ORDER BY document->>'proposed_at' ASC NULLS LAST
            """
        ),
        {"case_id": case_id},
    ).scalars()
    return [load_json(row) for row in rows]


def replace_action(conn: Connection, document: dict[str, Any], *, actor: dict[str, Any]) -> dict[str, Any]:
    conn.execute(
        text(
            """
            UPDATE actions SET
                status = :status,
                decided_by = CAST(:decided_by AS jsonb),
                decided_at = :decided_at,
                execution_result = CAST(:execution_result AS jsonb),
                document = CAST(:document AS jsonb)
            WHERE action_id = CAST(:action_id AS uuid)
            """
        ),
        {
            "action_id": document["action_id"],
            "status": document["status"],
            "decided_by": None if document.get("decided_by") is None else dump_json(document["decided_by"]),
            "decided_at": parse_ts(document.get("decided_at")),
            "execution_result": (
                None if document.get("execution_result") is None else dump_json(document["execution_result"])
            ),
            "document": dump_json(document),
        },
    )
    record_event(
        conn,
        event_type=action_event_type(document["status"]),
        actor=actor,
        case_id=document["case_id"],
        data={"action_id": document["action_id"], "status": document["status"]},
    )
    return document


def count_proposed(conn: Connection, case_id: str) -> int:
    return int(
        conn.execute(
            text(
                """
                SELECT count(*) FROM actions
                WHERE case_id = CAST(:case_id AS uuid) AND status = 'proposed'
                """
            ),
            {"case_id": case_id},
        ).scalar_one()
    )