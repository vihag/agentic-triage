"""Append an audit row.

T04 records a schema-shaped event in the same transaction as the state change.
T05 replaces the hash step with the hash chain; callers keep this signature.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from triage_db.jsonutil import dump_json, format_ts, parse_ts


def record_event(
    conn: Connection,
    *,
    event_type: str,
    actor: Mapping[str, Any],
    data: Mapping[str, Any] | None = None,
    case_id: str | None = None,
    alert_id: str | None = None,
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    seq = int(conn.execute(text("SELECT nextval('audit_events_seq')")).scalar_one())
    moment = occurred_at or datetime.now(timezone.utc)
    event: dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "seq": seq,
        "occurred_at": format_ts(moment),
        "type": event_type,
        "actor": dict(actor),
        "case_id": case_id,
        "alert_id": alert_id,
        "data": dict(data or {}),
        "prev_hash": None,
    }
    event["hash"] = _hash_event(event)
    _insert(conn, event)
    return event


def _hash_event(event: Mapping[str, Any]) -> str:
    body = {key: event[key] for key in event if key != "hash"}
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _insert(conn: Connection, event: Mapping[str, Any]) -> None:
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
            "seq": event["seq"],
            "event_id": event["event_id"],
            "occurred_at": parse_ts(event["occurred_at"]),
            "type": event["type"],
            "actor": dump_json(event["actor"]),
            "case_id": event["case_id"],
            "alert_id": event["alert_id"],
            "data": dump_json(event["data"]),
            "prev_hash": event["prev_hash"],
            "hash": event["hash"],
            "document": dump_json(event),
        },
    )
