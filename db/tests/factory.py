"""Insert a queued case and the alert and decision it depends on."""

from __future__ import annotations

import uuid

from sqlalchemy.engine import Connection
from triage_db.repositories import save_alert, save_case, save_decision


def seed_queued_case(
    conn: Connection,
    *,
    queue: str = "soc-high",
    priority: int = 10,
    created_at: str = "2026-11-18T01:00:00Z",
    assignee: str | None = "analyst-priya",
    title: str = "queued case",
) -> dict:
    alert_id = str(uuid.uuid4())
    decision_id = str(uuid.uuid4())
    case_id = str(uuid.uuid4())
    sid = f"sid-{case_id}"
    save_alert(
        conn,
        {
            "alert_id": alert_id,
            "source": {
                "system": "splunk",
                "instance": "splunk-onprem-sg1",
                "sid": sid,
                "search_name": "queue-seed",
            },
            "received_at": created_at,
            "splunk_severity": "medium",
            "title": title,
            "entities": {},
            "dedup_key": f"dedup-{case_id}",
            "raw": {"sid": sid},
        },
    )
    save_decision(
        conn,
        {
            "decision_id": decision_id,
            "alert_id": alert_id,
            "decided_at": created_at,
            "agent_version": "triage-agent/0.1.0",
            "original_severity": "medium",
            "final_severity": "high",
            "direction": "escalated",
            "disposition": "enqueue_for_triage",
            "confidence": 0.9,
            "candidate_labels": [],
            "rule_results": [],
            "fuzzy_result": None,
            "policy": {"policy_id": "severity-routing", "version": "2026-11-18", "rationale": "seed"},
        },
    )
    document = {
        "case_id": case_id,
        "alert_ids": [alert_id],
        "decision_id": decision_id,
        "title": title,
        "severity": "high",
        "original_severity": "medium",
        "direction": "escalated",
        "status": "queued",
        "queue": queue,
        "priority": priority,
        "assignee": assignee,
        "claimed_by": None,
        "lease_expires_at": None,
        "candidate_labels": [],
        "resolution": None,
        "created_at": created_at,
        "updated_at": created_at,
        "version": 1,
    }
    save_case(conn, document)
    return document
