"""Case reads and optimistic updates."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from triage_db.audit import record_event
from triage_db.jsonutil import dump_json, load_json, parse_ts
from triage_db.repositories.cases import OPEN_STATUSES
from triage_db.repositories.reference import ensure_analyst


class VersionMismatchError(Exception):
    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"expected version {expected}, got {actual}")


class IllegalTransitionError(Exception):
    def __init__(self, from_status: str, to_status: str) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"cannot transition {from_status} -> {to_status}")


def list_cases(
    conn: Connection,
    *,
    queue: str | None = None,
    status: list[str] | None = None,
    assignee: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: dict[str, Any] = {"limit": min(max(limit, 1), 200)}
    if queue:
        clauses.append("queue = :queue")
        params["queue"] = queue
    if assignee:
        clauses.append("assignee = :assignee")
        params["assignee"] = assignee
    if status:
        clauses.append("status = ANY(:statuses)")
        params["statuses"] = status
    sql = f"""
        SELECT document FROM cases
        WHERE {" AND ".join(clauses)}
        ORDER BY priority DESC, created_at ASC
        LIMIT :limit
    """
    rows = conn.execute(text(sql), params).scalars()
    return [load_json(row) for row in rows]


def replace_case(
    conn: Connection,
    document: dict[str, Any],
    *,
    expected_version: int | None,
    actor: dict[str, Any],
    audit_type: str = "case.status_changed",
) -> dict[str, Any]:
    case_id = document["case_id"]
    if expected_version is not None:
        current = conn.execute(
            text("SELECT version FROM cases WHERE case_id = CAST(:case_id AS uuid)"),
            {"case_id": case_id},
        ).scalar_one_or_none()
        if current is None:
            raise LookupError(case_id)
        if int(current) != int(expected_version):
            raise VersionMismatchError(int(expected_version), int(current))
    assignee = document.get("assignee")
    if assignee:
        ensure_analyst(conn, assignee)
    claimed_by = document.get("claimed_by")
    resolution = document.get("resolution")
    updated = conn.execute(
        text(
            """
            UPDATE cases SET
                title = :title,
                severity = :severity,
                status = :status,
                queue = :queue,
                priority = :priority,
                assignee = :assignee,
                claimed_by = CAST(:claimed_by AS jsonb),
                lease_expires_at = :lease_expires_at,
                candidate_labels = CAST(:candidate_labels AS jsonb),
                resolution = CAST(:resolution AS jsonb),
                version = :version,
                updated_at = :updated_at,
                document = CAST(:document AS jsonb)
            WHERE case_id = CAST(:case_id AS uuid)
            """
        ),
        {
            "case_id": case_id,
            "title": document["title"],
            "severity": document["severity"],
            "status": document["status"],
            "queue": document["queue"],
            "priority": document["priority"],
            "assignee": assignee,
            "claimed_by": None if claimed_by is None else dump_json(claimed_by),
            "lease_expires_at": parse_ts(document.get("lease_expires_at")),
            "candidate_labels": dump_json(document.get("candidate_labels") or []),
            "resolution": None if resolution is None else dump_json(resolution),
            "version": document["version"],
            "updated_at": parse_ts(document["updated_at"]),
            "document": dump_json(document),
        },
    )
    if updated.rowcount != 1:
        raise LookupError(case_id)
    case_open = document["status"] in OPEN_STATUSES
    conn.execute(
        text(
            """
            UPDATE alerts SET case_open = :case_open
            WHERE case_id = CAST(:case_id AS uuid)
            """
        ),
        {"case_id": case_id, "case_open": case_open},
    )
    record_event(
        conn,
        event_type=audit_type,
        actor=actor,
        case_id=case_id,
        data={"status": document["status"], "version": document["version"]},
    )
    return document


def bump_version(document: dict[str, Any], **patch: Any) -> dict[str, Any]:
    from datetime import UTC, datetime

    merged = {**document, **patch}
    merged["version"] = int(document["version"]) + 1
    merged["updated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return merged