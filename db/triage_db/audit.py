"""Hash-chained audit log.

``hash`` is ``sha256((prev_hash or "") + canonical_json(event without hash))``.
Canonical JSON sorts keys and has no insignificant whitespace. A null
``prev_hash`` contributes an empty prefix; the null is still inside the JSON.
Writers take a transaction advisory lock so the chain has no forks.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from triage_db.jsonutil import dump_json, format_ts, load_json, parse_ts
from triage_db.validation import validate_audit_event

SYSTEM_ACTOR: dict[str, str] = {"type": "system", "id": "triage-db"}
_CHAIN_LOCK = 84215045

_CASE_INSERT_EVENT = {
    "queued": "case.queued",
    "auto_closed": "case.auto_closed",
    "claimed": "case.created",
    "in_progress": "case.created",
    "awaiting_approval": "case.created",
    "resolved": "case.created",
    "false_positive": "case.created",
    "closed": "case.created",
}

# audit-event.schema.json has no action.executing or action.expired.
# data.status keeps the real status; the type is the nearest enum value.
_ACTION_EVENT = {
    "proposed": "action.proposed",
    "approved": "action.approved",
    "rejected": "action.rejected",
    "executing": "action.executed",
    "executed": "action.executed",
    "failed": "action.failed",
    "expired": "action.rejected",
}


class AuditChainError(Exception):
    def __init__(self, seq: int, reason: str) -> None:
        self.seq = seq
        super().__init__(f"audit chain broken at seq {seq}: {reason}")


def case_insert_event(status: str) -> str:
    try:
        return _CASE_INSERT_EVENT[status]
    except KeyError as exc:
        raise ValueError(f"unknown case status {status}") from exc


def action_event_type(status: str) -> str:
    try:
        return _ACTION_EVENT[status]
    except KeyError as exc:
        raise ValueError(f"unknown action status {status}") from exc


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
    conn.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": _CHAIN_LOCK})
    prev_hash = conn.execute(text("SELECT hash FROM audit_events ORDER BY seq DESC LIMIT 1")).scalar()
    seq = int(conn.execute(text("SELECT nextval('audit_events_seq')")).scalar_one())
    moment = occurred_at or datetime.now(UTC)
    event: dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "seq": seq,
        "occurred_at": format_ts(moment),
        "type": event_type,
        "actor": dict(actor),
        "case_id": case_id,
        "alert_id": alert_id,
        "data": dict(data or {}),
        "prev_hash": prev_hash,
    }
    event["hash"] = chain_hash(prev_hash, _body(event))
    validate_audit_event(event)
    _insert(conn, event)
    return event


def verify_chain(conn: Connection) -> int:
    """Walk ``audit_events`` in seq order. Raise ``AuditChainError`` on a bad row."""
    rows = conn.execute(
        text(
            """
            SELECT seq, occurred_at, type, actor, case_id::text AS case_id, alert_id::text AS alert_id,
                   data, prev_hash, hash, document
            FROM audit_events
            ORDER BY seq
            """
        )
    ).all()
    previous: str | None = None
    for row in rows:
        document = load_json(row.document)
        if document.get("prev_hash") != previous or row.prev_hash != previous:
            raise AuditChainError(row.seq, "prev_hash does not match the previous event")
        expected = chain_hash(previous, _body(document))
        if document.get("hash") != expected or row.hash != expected:
            raise AuditChainError(row.seq, "hash does not match the canonical event")
        if load_json(row.data) != document["data"] or row.type != document["type"]:
            raise AuditChainError(row.seq, "columns do not match the hashed document")
        if load_json(row.actor) != document["actor"]:
            raise AuditChainError(row.seq, "actor column does not match the hashed document")
        occurred = parse_ts(document["occurred_at"])
        if occurred != row.occurred_at:
            raise AuditChainError(row.seq, "occurred_at column does not match the hashed document")
        if document.get("case_id") != row.case_id or document.get("alert_id") != row.alert_id:
            raise AuditChainError(row.seq, "case or alert id does not match the hashed document")
        previous = expected
    return len(rows)


def chain_hash(prev_hash: str | None, body: Mapping[str, Any]) -> str:
    prefix = prev_hash or ""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((prefix + canonical).encode()).hexdigest()


def _body(event: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if key != "hash"}


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
