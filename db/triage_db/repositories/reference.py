"""Reference rows: SIEM instances, analysts, bots, rules, incident corpus."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from triage_db.jsonutil import dump_json


def ensure_siem(conn: Connection, instance_id: str, kind: str) -> None:
    if kind not in ("splunk", "simulator"):
        raise ValueError(f"siem kind must be splunk or simulator, got {kind!r}")
    conn.execute(
        text(
            """
            INSERT INTO siem_instances (instance_id, kind)
            VALUES (:instance_id, :kind)
            ON CONFLICT (instance_id) DO NOTHING
            """
        ),
        {"instance_id": instance_id, "kind": kind},
    )


def ensure_analyst(conn: Connection, analyst_id: str, display_name: str | None = None) -> None:
    conn.execute(
        text(
            """
            INSERT INTO analysts (analyst_id, display_name, email, on_shift)
            VALUES (:analyst_id, :display_name, :email, false)
            ON CONFLICT (analyst_id) DO NOTHING
            """
        ),
        {
            "analyst_id": analyst_id,
            "display_name": display_name or analyst_id,
            "email": f"{analyst_id}@example.invalid",
        },
    )


def save_bot_credential(
    conn: Connection,
    *,
    bot_id: str,
    on_behalf_of: str,
    key_hash: str,
    revoked: bool = False,
    created_at: datetime | None = None,
) -> None:
    ensure_analyst(conn, on_behalf_of)
    conn.execute(
        text(
            """
            INSERT INTO bot_credentials (bot_id, on_behalf_of, key_hash, revoked, created_at)
            VALUES (:bot_id, :on_behalf_of, :key_hash, :revoked, COALESCE(:created_at, now()))
            """
        ),
        {
            "bot_id": bot_id,
            "on_behalf_of": on_behalf_of,
            "key_hash": key_hash,
            "revoked": revoked,
            "created_at": created_at,
        },
    )


def save_bot_run(
    conn: Connection,
    *,
    run_id: str,
    bot_id: str,
    routine_id: str,
    status: str,
    cases_processed: int = 0,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO bot_runs (
                run_id, bot_id, routine_id, status, cases_processed, started_at, finished_at
            ) VALUES (
                CAST(:run_id AS uuid), :bot_id, :routine_id, :status, :cases_processed,
                COALESCE(:started_at, now()), :finished_at
            )
            """
        ),
        {
            "run_id": run_id,
            "bot_id": bot_id,
            "routine_id": routine_id,
            "status": status,
            "cases_processed": cases_processed,
            "started_at": started_at,
            "finished_at": finished_at,
        },
    )


def save_rule(
    conn: Connection,
    *,
    rule_id: str,
    version: str,
    enabled: bool,
    priority: int,
    config: dict[str, Any],
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO rules (rule_id, version, enabled, priority, config)
            VALUES (:rule_id, :version, :enabled, :priority, CAST(:config AS jsonb))
            """
        ),
        {
            "rule_id": rule_id,
            "version": version,
            "enabled": enabled,
            "priority": priority,
            "config": dump_json(config),
        },
    )


def save_incident(
    conn: Connection,
    *,
    ref_id: str,
    ref_type: str,
    summary: str,
    embedding: list[float],
    verified_severity: str | None = None,
    verdict: str | None = None,
) -> None:
    if len(embedding) != 1536:
        raise ValueError("incident embeddings are vector(1536)")
    literal = "[" + ",".join(repr(float(value)) for value in embedding) + "]"
    conn.execute(
        text(
            """
            INSERT INTO incident_corpus (
                ref_id, ref_type, summary, verified_severity, verdict, embedding
            ) VALUES (
                :ref_id, :ref_type, :summary, :verified_severity, :verdict, CAST(:embedding AS vector)
            )
            """
        ),
        {
            "ref_id": ref_id,
            "ref_type": ref_type,
            "summary": summary,
            "verified_severity": verified_severity,
            "verdict": verdict,
            "embedding": literal,
        },
    )
