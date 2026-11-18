"""Case queue and triage outbox.

Case claims follow ADR-0003: one UPDATE whose subquery is
``SELECT ... ORDER BY priority DESC, created_at ASC FOR UPDATE SKIP LOCKED``.
Bot claims pass the analyst id; analyst claims pass no assignee filter.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from triage_db.audit import record_event
from triage_db.jsonutil import dump_json, load_json

REAPER_ACTOR = {"type": "system", "id": "lease-reaper"}

CLAIM_SQL = """
WITH picked AS (
    SELECT case_id
    FROM cases
    WHERE queue = :queue
      AND status = 'queued'
      AND (CAST(:assignee AS text) IS NULL OR assignee = :assignee)
    ORDER BY priority DESC, created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT :max_items
)
UPDATE cases AS c
SET status = 'claimed',
    claimed_by = CAST(:claimed_by AS jsonb),
    lease_expires_at = date_trunc('second', now() + make_interval(secs => :lease_seconds)),
    version = c.version + 1,
    updated_at = date_trunc('second', now()),
    document = c.document || jsonb_build_object(
        'status', 'claimed',
        'claimed_by', CAST(:claimed_by AS jsonb),
        'lease_expires_at', to_char(
            date_trunc('second', now() + make_interval(secs => :lease_seconds)) AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS"Z"'
        ),
        'version', c.version + 1,
        'updated_at', to_char(
            date_trunc('second', now()) AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS"Z"'
        )
    )
FROM picked
WHERE c.case_id = picked.case_id
RETURNING c.document
"""

RELEASE_SQL = """
UPDATE cases
SET status = 'queued',
    claimed_by = NULL,
    lease_expires_at = NULL,
    version = version + 1,
    updated_at = date_trunc('second', now()),
    document = document || jsonb_build_object(
        'status', 'queued',
        'claimed_by', 'null'::jsonb,
        'lease_expires_at', 'null'::jsonb,
        'version', version + 1,
        'updated_at', to_char(date_trunc('second', now()) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
    )
WHERE case_id = CAST(:case_id AS uuid)
  AND status = 'claimed'
  AND claimed_by->>'id' = :releaser_id
RETURNING document
"""

REAP_SQL = """
WITH expired AS (
    SELECT case_id
    FROM cases
    WHERE status = 'claimed'
      AND lease_expires_at IS NOT NULL
      AND lease_expires_at <= now()
    FOR UPDATE SKIP LOCKED
)
UPDATE cases AS c
SET status = 'queued',
    claimed_by = NULL,
    lease_expires_at = NULL,
    version = c.version + 1,
    updated_at = date_trunc('second', now()),
    document = c.document || jsonb_build_object(
        'status', 'queued',
        'claimed_by', 'null'::jsonb,
        'lease_expires_at', 'null'::jsonb,
        'version', c.version + 1,
        'updated_at', to_char(date_trunc('second', now()) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
    )
FROM expired
WHERE c.case_id = expired.case_id
RETURNING c.case_id::text AS case_id, c.document
"""

OUTBOX_CLAIM_SQL = """
WITH picked AS (
    SELECT id
    FROM triage_outbox
    WHERE status = 'pending'
       OR (status = 'processing' AND lease_expires_at IS NOT NULL AND lease_expires_at <= now())
    ORDER BY id ASC
    FOR UPDATE SKIP LOCKED
    LIMIT :max_items
)
UPDATE triage_outbox AS o
SET status = 'processing',
    attempts = o.attempts + 1,
    lease_expires_at = date_trunc('second', now() + make_interval(secs => :lease_seconds))
FROM picked
WHERE o.id = picked.id
RETURNING o.id, o.alert_id::text AS alert_id, o.status, o.attempts, o.lease_expires_at
"""


@dataclass(frozen=True)
class OutboxClaim:
    id: int
    alert_id: str
    status: str
    attempts: int
    lease_expires_at: datetime


def claim_next(
    conn: Connection,
    *,
    queue: str,
    claimed_by: dict[str, Any],
    max_items: int = 1,
    lease_seconds: int = 900,
) -> list[dict[str, Any]]:
    """Claim the next queued cases. ``assignee`` is unrestricted (analyst claimNext)."""
    return _claim(
        conn,
        queue=queue,
        claimed_by=claimed_by,
        assignee=None,
        max_items=max_items,
        lease_seconds=lease_seconds,
    )


def bot_claim(
    conn: Connection,
    *,
    queue: str,
    claimed_by: dict[str, Any],
    max_items: int = 1,
    lease_seconds: int = 900,
) -> list[dict[str, Any]]:
    """Claim only cases assigned to this bot's analyst."""
    if claimed_by.get("type") != "grok_bot":
        raise ValueError("bot_claim requires a grok_bot principal")
    analyst_id = claimed_by.get("on_behalf_of")
    if not isinstance(analyst_id, str) or not analyst_id:
        raise ValueError("grok_bot principal requires on_behalf_of")
    return _claim(
        conn,
        queue=queue,
        claimed_by=claimed_by,
        assignee=analyst_id,
        max_items=max_items,
        lease_seconds=lease_seconds,
    )


def release_case(conn: Connection, *, case_id: str, released_by: dict[str, Any]) -> dict[str, Any]:
    releaser_id = released_by.get("id")
    if not isinstance(releaser_id, str) or not releaser_id:
        raise ValueError("release requires a principal id")
    row = conn.execute(
        text(RELEASE_SQL), {"case_id": case_id, "releaser_id": releaser_id}
    ).one_or_none()
    if row is None:
        raise LookupError(f"case {case_id} is not claimed by {releaser_id}")
    document = load_json(row[0])
    record_event(
        conn,
        event_type="case.released",
        actor=released_by,
        case_id=case_id,
        data={"version": document["version"]},
    )
    return document


def reap_expired_leases(conn: Connection) -> list[dict[str, Any]]:
    """Return expired claims to queued and emit ``case.lease_expired`` for each."""
    rows = conn.execute(text(REAP_SQL)).all()
    released: list[dict[str, Any]] = []
    for row in rows:
        document = load_json(row.document)
        record_event(
            conn,
            event_type="case.lease_expired",
            actor=REAPER_ACTOR,
            case_id=row.case_id,
            data={"version": document["version"]},
        )
        released.append(document)
    return released


def claim_outbox(conn: Connection, *, max_items: int = 1, lease_seconds: int = 60) -> list[OutboxClaim]:
    """Claim pending outbox rows, and processing rows whose lease has expired."""
    _check_bounds(max_items, lease_seconds)
    rows = conn.execute(
        text(OUTBOX_CLAIM_SQL),
        {"max_items": max_items, "lease_seconds": lease_seconds},
    ).all()
    return [
        OutboxClaim(
            id=row.id,
            alert_id=row.alert_id,
            status=row.status,
            attempts=row.attempts,
            lease_expires_at=row.lease_expires_at,
        )
        for row in rows
    ]


def complete_outbox(conn: Connection, outbox_id: int) -> None:
    updated = conn.execute(
        text(
            """
            UPDATE triage_outbox
            SET status = 'done', lease_expires_at = NULL
            WHERE id = :id AND status = 'processing'
            """
        ),
        {"id": outbox_id},
    )
    if updated.rowcount != 1:
        raise LookupError(f"outbox {outbox_id} is not processing")


def _claim(
    conn: Connection,
    *,
    queue: str,
    claimed_by: dict[str, Any],
    assignee: str | None,
    max_items: int,
    lease_seconds: int,
) -> list[dict[str, Any]]:
    _check_bounds(max_items, lease_seconds)
    rows = conn.execute(
        text(CLAIM_SQL),
        {
            "queue": queue,
            "assignee": assignee,
            "max_items": max_items,
            "lease_seconds": lease_seconds,
            "claimed_by": dump_json(claimed_by),
        },
    ).scalars()
    claimed = [load_json(document) for document in rows]
    for document in claimed:
        record_event(
            conn,
            event_type="case.claimed",
            actor=claimed_by,
            case_id=document["case_id"],
            data={"queue": queue, "version": document["version"]},
        )
    return claimed


def _check_bounds(max_items: int, lease_seconds: int) -> None:
    if max_items < 1:
        raise ValueError("max_items must be at least 1")
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be at least 1")
