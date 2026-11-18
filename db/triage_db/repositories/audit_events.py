"""Store and re-read an AuditEvent document.

This path writes the caller's event, including its hash, unchanged. The
hash-chain writer (T05) is a different entry point and computes the hash.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from triage_db.jsonutil import dump_json, load_json, parse_ts


def save_audit_event(conn: Connection, document: dict[str, Any]) -> None:
    conn.execute(
        text(
            """
            INSERT INTO audit_events (
                seq, event_id, occurred_at, type, actor, case_id, alert_id,
                data, prev_hash, hash, document
            ) VALUES (
                :seq, CAST(:event_id AS uuid), :occurred_at, :type, CAST(:actor AS jsonb),
                CAST(:case_id AS uuid), CAST(:alert_id AS uuid), CAST(:data AS jsonb),
                :prev_hash, :hash, CAST(:document AS jsonb)
            )
            """
        ),
        {
            "seq": document["seq"],
            "event_id": document["event_id"],
            "occurred_at": parse_ts(document["occurred_at"]),
            "type": document["type"],
            "actor": dump_json(document["actor"]),
            "case_id": document.get("case_id"),
            "alert_id": document.get("alert_id"),
            "data": dump_json(document["data"]),
            "prev_hash": document.get("prev_hash"),
            "hash": document["hash"],
            "document": dump_json(document),
        },
    )
    conn.execute(
        text(
            """
            SELECT setval(
                'audit_events_seq',
                GREATEST(:seq, (SELECT last_value FROM audit_events_seq))
            )
            """
        ),
        {"seq": document["seq"]},
    )


def get_audit_event(conn: Connection, event_id: str) -> dict[str, Any]:
    document = conn.execute(
        text("SELECT document FROM audit_events WHERE event_id = CAST(:event_id AS uuid)"),
        {"event_id": event_id},
    ).scalar_one()
    return load_json(document)
