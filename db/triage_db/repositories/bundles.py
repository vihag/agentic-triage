"""Case bundle is a read model assembled from stored rows, not its own table."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from triage_db.jsonutil import load_json
from triage_db.repositories.cases import get_case
from triage_db.repositories.decisions import get_decision
from triage_db.repositories.evidence import get_evidence_pack
from triage_db.repositories.next_steps import get_next_steps_pack


def compose_case_bundle(conn: Connection, case_id: str, *, generated_at: str) -> dict[str, Any]:
    case = get_case(conn, case_id)
    evidence_id = case.get("evidence_pack_id")
    next_steps_id = case.get("next_steps_pack_id")
    proposed = conn.execute(
        text(
            """
            SELECT document FROM actions
            WHERE case_id = CAST(:case_id AS uuid) AND status = 'proposed'
            ORDER BY action_id
            """
        ),
        {"case_id": case_id},
    ).scalars()
    return {
        "case": case,
        "decision": get_decision(conn, case["decision_id"]),
        "evidence_pack": None if not evidence_id else get_evidence_pack(conn, evidence_id),
        "next_steps_pack": None if not next_steps_id else get_next_steps_pack(conn, next_steps_id),
        "proposed_actions": [load_json(document) for document in proposed],
        "generated_at": generated_at,
    }
