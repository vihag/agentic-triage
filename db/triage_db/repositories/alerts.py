"""Alert and transactional outbox persistence."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from triage_db.audit import SYSTEM_ACTOR, record_event
from triage_db.jsonutil import dump_json, load_json, parse_ts
from triage_db.repositories.reference import ensure_siem


def save_alert(
    conn: Connection, document: dict[str, Any], *, actor: Mapping[str, Any] | None = None
) -> None:
    source = document["source"]
    instance_id = source.get("instance") or "unknown"
    ensure_siem(conn, instance_id, source["system"])
    conn.execute(
        text(
            """
            INSERT INTO alerts (
                alert_id, instance_id, sid, search_name, splunk_severity,
                received_at, event_time, title, entities, dedup_key, raw, document
            ) VALUES (
                CAST(:alert_id AS uuid), :instance_id, :sid, :search_name, :splunk_severity,
                :received_at, :event_time, :title,
                CAST(:entities AS jsonb), :dedup_key, CAST(:raw AS jsonb), CAST(:document AS jsonb)
            )
            """
        ),
        {
            "alert_id": document["alert_id"],
            "instance_id": instance_id,
            "sid": source["sid"],
            "search_name": source["search_name"],
            "splunk_severity": document["splunk_severity"],
            "received_at": parse_ts(document["received_at"]),
            "event_time": parse_ts(document.get("event_time")),
            "title": document["title"],
            "entities": dump_json(document["entities"]),
            "dedup_key": document["dedup_key"],
            "raw": dump_json(document["raw"]),
            "document": dump_json(document),
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO triage_outbox (alert_id, status, attempts)
            VALUES (CAST(:alert_id AS uuid), 'pending', 0)
            """
        ),
        {"alert_id": document["alert_id"]},
    )
    record_event(
        conn,
        event_type="alert.received",
        actor=dict(actor) if actor is not None else dict(SYSTEM_ACTOR),
        alert_id=document["alert_id"],
        data={"sid": source["sid"], "alert_id": document["alert_id"]},
    )


def get_alert(conn: Connection, alert_id: str) -> dict[str, Any]:
    document = conn.execute(
        text("SELECT document FROM alerts WHERE alert_id = CAST(:alert_id AS uuid)"),
        {"alert_id": alert_id},
    ).scalar_one()
    return load_json(document)


def find_alert_by_sid(conn: Connection, sid: str) -> dict[str, Any] | None:
    row = conn.execute(
        text("SELECT document FROM alerts WHERE sid = :sid"),
        {"sid": sid},
    ).first()
    if row is None:
        return None
    return load_json(row.document)


def get_raw(conn: Connection, alert_id: str) -> dict[str, Any]:
    raw = conn.execute(
        text("SELECT raw FROM alerts WHERE alert_id = CAST(:alert_id AS uuid)"),
        {"alert_id": alert_id},
    ).scalar_one()
    return load_json(raw)


def save_webhook_payload(conn: Connection, payload: dict[str, Any]) -> str:
    """Store a Splunk webhook verbatim in alerts.raw.

    The ER diagram has no webhook table. alerts.raw is the original body.
    The shell around it is only there so the payload has a row to live in.
    """
    alert_id = str(uuid.uuid4())
    sid = str(payload["sid"])
    search_name = str(payload.get("search_name") or sid)
    save_alert(
        conn,
        {
            "alert_id": alert_id,
            "source": {
                "system": "splunk",
                "instance": "webhook-archive",
                "sid": sid,
                "search_name": search_name,
            },
            "received_at": "2026-11-18T00:00:00Z",
            "splunk_severity": "informational",
            "title": search_name,
            "entities": {},
            "dedup_key": f"webhook:{sid}",
            "raw": payload,
        },
    )
    return alert_id
