"""Case persistence. Linking a case sets alerts.case_id and alerts.case_open."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from triage_db.jsonutil import dump_json, load_json, parse_ts
from triage_db.repositories.reference import ensure_analyst

OPEN_STATUSES = frozenset({"queued", "claimed", "in_progress", "awaiting_approval"})


def save_case(conn: Connection, document: dict[str, Any]) -> None:
    assignee = document.get("assignee")
    if assignee:
        ensure_analyst(conn, assignee)
    claimed_by = document.get("claimed_by")
    resolution = document.get("resolution")
    conn.execute(
        text(
            """
            INSERT INTO cases (
                case_id, decision_id, title, severity, original_severity, direction,
                status, queue, priority, assignee, claimed_by, lease_expires_at,
                candidate_labels, resolution, version, created_at, updated_at, document
            ) VALUES (
                CAST(:case_id AS uuid), CAST(:decision_id AS uuid), :title, :severity,
                :original_severity, :direction, :status, :queue, :priority, :assignee,
                CAST(:claimed_by AS jsonb), :lease_expires_at, CAST(:candidate_labels AS jsonb),
                CAST(:resolution AS jsonb), :version, :created_at, :updated_at, CAST(:document AS jsonb)
            )
            """
        ),
        {
            "case_id": document["case_id"],
            "decision_id": document["decision_id"],
            "title": document["title"],
            "severity": document["severity"],
            "original_severity": document["original_severity"],
            "direction": document["direction"],
            "status": document["status"],
            "queue": document["queue"],
            "priority": document["priority"],
            "assignee": assignee,
            "claimed_by": None if claimed_by is None else dump_json(claimed_by),
            "lease_expires_at": parse_ts(document.get("lease_expires_at")),
            "candidate_labels": dump_json(document["candidate_labels"]),
            "resolution": None if resolution is None else dump_json(resolution),
            "version": document["version"],
            "created_at": parse_ts(document["created_at"]),
            "updated_at": parse_ts(document["updated_at"]),
            "document": dump_json(document),
        },
    )
    case_open = document["status"] in OPEN_STATUSES
    for alert_id in document["alert_ids"]:
        updated = conn.execute(
            text(
                """
                UPDATE alerts
                SET case_id = CAST(:case_id AS uuid), case_open = :case_open
                WHERE alert_id = CAST(:alert_id AS uuid)
                """
            ),
            {"case_id": document["case_id"], "alert_id": alert_id, "case_open": case_open},
        )
        if updated.rowcount != 1:
            raise LookupError(f"alert {alert_id} is not stored; cannot group it into {document['case_id']}")


def get_case(conn: Connection, case_id: str) -> dict[str, Any]:
    document = conn.execute(
        text("SELECT document FROM cases WHERE case_id = CAST(:case_id AS uuid)"),
        {"case_id": case_id},
    ).scalar_one()
    return load_json(document)
