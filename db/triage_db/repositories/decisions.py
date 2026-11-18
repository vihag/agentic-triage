"""TriageDecision persistence. One decision per alert."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from triage_db.audit import SYSTEM_ACTOR, record_event
from triage_db.jsonutil import dump_json, load_json, parse_ts


def save_decision(
    conn: Connection, document: dict[str, Any], *, actor: Mapping[str, Any] | None = None
) -> None:
    fuzzy = document["fuzzy_result"]
    conn.execute(
        text(
            """
            INSERT INTO triage_decisions (
                decision_id, alert_id, original_severity, final_severity, direction,
                disposition, confidence, candidate_labels, rule_results, fuzzy_result,
                policy, agent_version, decided_at, document
            ) VALUES (
                CAST(:decision_id AS uuid), CAST(:alert_id AS uuid), :original_severity,
                :final_severity, :direction, :disposition, :confidence,
                CAST(:candidate_labels AS jsonb), CAST(:rule_results AS jsonb),
                CAST(:fuzzy_result AS jsonb), CAST(:policy AS jsonb),
                :agent_version, :decided_at, CAST(:document AS jsonb)
            )
            """
        ),
        {
            "decision_id": document["decision_id"],
            "alert_id": document["alert_id"],
            "original_severity": document["original_severity"],
            "final_severity": document["final_severity"],
            "direction": document["direction"],
            "disposition": document["disposition"],
            "confidence": document["confidence"],
            "candidate_labels": dump_json(document["candidate_labels"]),
            "rule_results": dump_json(document["rule_results"]),
            "fuzzy_result": None if fuzzy is None else dump_json(fuzzy),
            "policy": dump_json(document["policy"]),
            "agent_version": document["agent_version"],
            "decided_at": parse_ts(document["decided_at"]),
            "document": dump_json(document),
        },
    )
    record_event(
        conn,
        event_type="triage.decided",
        actor=dict(actor) if actor is not None else dict(SYSTEM_ACTOR),
        alert_id=document["alert_id"],
        data={
            "decision_id": document["decision_id"],
            "direction": document["direction"],
            "disposition": document["disposition"],
        },
    )


def get_decision_for_alert(conn: Connection, alert_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        text(
            """
            SELECT document FROM triage_decisions
            WHERE alert_id = CAST(:alert_id AS uuid)
            """
        ),
        {"alert_id": alert_id},
    ).first()
    if row is None:
        return None
    return load_json(row.document)


def get_decision(conn: Connection, decision_id: str) -> dict[str, Any]:
    document = conn.execute(
        text("SELECT document FROM triage_decisions WHERE decision_id = CAST(:decision_id AS uuid)"),
        {"decision_id": decision_id},
    ).scalar_one()
    return load_json(document)
