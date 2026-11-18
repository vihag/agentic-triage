"""Hash chain: every write emits a schema-valid event, and tampering is detected."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from tests.factory import seed_queued_case
from triage_db.audit import AuditChainError, action_event_type, record_event, verify_chain
from triage_db.queue import claim_next, reap_expired_leases, release_case
from triage_db.repositories import (
    save_action,
    save_alert,
    save_case,
    save_decision,
    save_evidence_pack,
    save_next_steps_pack,
)
from triage_db.validation import validate_audit_event

ANALYST = {"type": "analyst", "id": "analyst-priya"}
WHEN = "2026-11-18T04:00:00Z"


def _types(conn: Connection) -> list[str]:
    return list(conn.execute(text("SELECT type FROM audit_events ORDER BY seq")).scalars())


def test_write_paths_emit_schema_valid_events_in_one_chain(conn: Connection) -> None:
    seeded = seed_queued_case(conn, created_at=WHEN)
    case_id = seeded["case_id"]
    alert_id = seeded["alert_ids"][0]
    save_evidence_pack(
        conn,
        {
            "evidence_pack_id": str(uuid.uuid4()),
            "case_id": case_id,
            "alert_id": alert_id,
            "version": 1,
            "generated_at": WHEN,
            "generated_by": {"type": "triage_agent", "id": "triage-agent/0.1.0"},
            "summary": "Seeded evidence",
            "items": [
                {
                    "evidence_id": "ev-seed-1",
                    "kind": "raw_event",
                    "title": "Trigger",
                    "source": "test",
                    "collected_at": WHEN,
                    "added_by": {"type": "triage_agent", "id": "triage-agent/0.1.0"},
                }
            ],
            "timeline": [],
        },
    )
    save_next_steps_pack(
        conn,
        {
            "next_steps_pack_id": str(uuid.uuid4()),
            "case_id": case_id,
            "version": 1,
            "playbook_id": "pb-test",
            "steps": [
                {
                    "step_id": "s1",
                    "order": 1,
                    "phase": "investigate",
                    "title": "Look",
                    "description": "Look again",
                }
            ],
            "draft_responses": [],
        },
    )
    save_action(
        conn,
        {
            "action_id": str(uuid.uuid4()),
            "case_id": case_id,
            "type": "notify_owner",
            "params": {"user": "jdoe"},
            "rationale": "Tell the owner",
            "risk": "low",
            "status": "proposed",
            "requires_approval": True,
            "proposed_by": {"type": "triage_agent", "id": "triage-agent/0.1.0"},
            "proposed_at": WHEN,
        },
    )
    claim_next(conn, queue="soc-high", claimed_by=ANALYST)
    release_case(conn, case_id=case_id, released_by=ANALYST)
    claim_next(conn, queue="soc-high", claimed_by=ANALYST)
    conn.execute(
        text("UPDATE cases SET lease_expires_at = now() - interval '1 second' WHERE case_id = CAST(:id AS uuid)"),
        {"id": case_id},
    )
    reap_expired_leases(conn)

    assert _types(conn) == [
        "alert.received",
        "triage.decided",
        "case.queued",
        "evidence.appended",
        "next_steps.updated",
        "action.proposed",
        "case.claimed",
        "case.released",
        "case.claimed",
        "case.lease_expired",
    ]
    documents = conn.execute(text("SELECT document FROM audit_events ORDER BY seq")).scalars()
    for document in documents:
        validate_audit_event(document)
    assert verify_chain(conn) == 10


def test_audit_rolls_back_with_the_alert(engine: Engine, conn: Connection) -> None:
    document = {
        "alert_id": str(uuid.uuid4()),
        "source": {
            "system": "simulator",
            "instance": "sim-1",
            "sid": "sid-rollback",
            "search_name": "rollback",
        },
        "received_at": WHEN,
        "splunk_severity": "low",
        "title": "rollback",
        "entities": {},
        "dedup_key": "dedup-rollback",
        "raw": {"sid": "sid-rollback"},
    }
    with engine.connect() as other:
        transaction = other.begin()
        save_alert(other, document)
        assert other.execute(text("SELECT count(*) FROM audit_events")).scalar_one() == 1
        transaction.rollback()

    assert conn.execute(text("SELECT count(*) FROM alerts")).scalar_one() == 0
    assert conn.execute(text("SELECT count(*) FROM audit_events")).scalar_one() == 0


def test_verify_chain_detects_a_tampered_row(conn: Connection) -> None:
    seed_queued_case(conn, created_at=WHEN)
    assert verify_chain(conn) == 3
    conn.execute(
        text(
            """
            UPDATE audit_events
            SET data = '{"tampered": true}'::jsonb,
                document = jsonb_set(document, '{data}', '{"tampered": true}'::jsonb)
            WHERE seq = (SELECT min(seq) FROM audit_events)
            """
        )
    )
    with pytest.raises(AuditChainError) as caught:
        verify_chain(conn)
    assert caught.value.seq == 1


def test_a_rolled_back_event_does_not_break_the_chain(engine: Engine, conn: Connection) -> None:
    record_event(conn, event_type="auth.denied", actor={"type": "system", "id": "triage-db"}, data={"n": 1})
    conn.commit()
    with engine.connect() as other:
        transaction = other.begin()
        record_event(other, event_type="auth.denied", actor={"type": "system", "id": "triage-db"}, data={"n": 2})
        transaction.rollback()
    record_event(conn, event_type="auth.denied", actor={"type": "system", "id": "triage-db"}, data={"n": 3})
    seqs = list(conn.execute(text("SELECT seq FROM audit_events ORDER BY seq")).scalars())
    assert seqs[1] > seqs[0] + 1
    assert verify_chain(conn) == 2


def test_bot_actor_without_analyst_is_rejected(conn: Connection) -> None:
    with pytest.raises(ValueError):
        record_event(
            conn,
            event_type="auth.denied",
            actor={"type": "grok_bot", "id": "grokbot-priya"},
            data={"reason": "missing on_behalf_of"},
        )
    assert conn.execute(text("SELECT count(*) FROM audit_events")).scalar_one() == 0


def test_auto_closed_insert_emits_case_auto_closed(conn: Connection) -> None:
    alert_id = str(uuid.uuid4())
    decision_id = str(uuid.uuid4())
    case_id = str(uuid.uuid4())
    save_alert(
        conn,
        {
            "alert_id": alert_id,
            "source": {
                "system": "splunk",
                "instance": "splunk-onprem-sg1",
                "sid": f"sid-{case_id}",
                "search_name": "auto-close",
            },
            "received_at": WHEN,
            "splunk_severity": "high",
            "title": "auto-close",
            "entities": {},
            "dedup_key": f"dedup-{case_id}",
            "raw": {"sid": f"sid-{case_id}"},
        },
    )
    save_decision(
        conn,
        {
            "decision_id": decision_id,
            "alert_id": alert_id,
            "decided_at": WHEN,
            "agent_version": "triage-agent/0.1.0",
            "original_severity": "high",
            "final_severity": "low",
            "direction": "downgraded",
            "disposition": "auto_closed",
            "confidence": 0.95,
            "candidate_labels": [],
            "rule_results": [],
            "fuzzy_result": None,
            "policy": {"policy_id": "severity-routing", "version": "2026-11-18", "rationale": "test"},
        },
    )
    save_case(
        conn,
        {
            "case_id": case_id,
            "alert_ids": [alert_id],
            "decision_id": decision_id,
            "title": "auto-close",
            "severity": "low",
            "original_severity": "high",
            "direction": "downgraded",
            "status": "auto_closed",
            "queue": "none",
            "priority": 0,
            "assignee": None,
            "claimed_by": None,
            "lease_expires_at": None,
            "candidate_labels": [],
            "resolution": None,
            "created_at": WHEN,
            "updated_at": WHEN,
            "version": 1,
        },
    )
    assert _types(conn)[-1] == "case.auto_closed"
    verify_chain(conn)


def _action(case_id: str, status: str) -> dict:
    document = {
        "action_id": str(uuid.uuid4()),
        "case_id": case_id,
        "type": "notify_owner",
        "params": {},
        "rationale": "status probe",
        "risk": "low",
        "status": status,
        "requires_approval": True,
        "proposed_by": {"type": "triage_agent", "id": "triage-agent/0.1.0"},
        "proposed_at": WHEN,
    }
    # action.schema.json: decided statuses (approved through failed) need an analyst
    # decider. An expired action was never decided.
    if status in {"approved", "rejected", "executing", "executed", "failed"}:
        document["decided_by"] = dict(ANALYST)
        document["decided_at"] = WHEN
    return document


def _last_event(conn: Connection):  # type: ignore[no-untyped-def]
    return conn.execute(
        text("SELECT type, actor, data FROM audit_events ORDER BY seq DESC LIMIT 1")
    ).one()


def test_expired_action_emits_action_expired(conn: Connection) -> None:
    seeded = seed_queued_case(conn, created_at=WHEN)
    action = _action(seeded["case_id"], "expired")
    save_action(conn, action)
    event = _last_event(conn)
    assert event.type == "action.expired"
    assert event.actor["type"] == "system"
    assert event.data["action_id"] == action["action_id"]
    assert event.data["status"] == "expired"
    rejected = conn.execute(
        text("SELECT count(*) FROM audit_events WHERE type = 'action.rejected'")
    ).scalar_one()
    assert rejected == 0
    verify_chain(conn)


def test_executing_action_emits_action_executing(conn: Connection) -> None:
    seeded = seed_queued_case(conn, created_at=WHEN)
    action = _action(seeded["case_id"], "executing")
    save_action(conn, action)
    event = _last_event(conn)
    assert event.type == "action.executing"
    assert event.data["action_id"] == action["action_id"]
    assert event.data["status"] == "executing"
    executed = conn.execute(
        text("SELECT count(*) FROM audit_events WHERE type = 'action.executed'")
    ).scalar_one()
    assert executed == 0
    verify_chain(conn)


def test_every_action_status_has_its_own_audit_event_type() -> None:
    contracts = Path(__file__).resolve().parents[2] / "contracts" / "schemas"
    statuses = json.loads((contracts / "action.schema.json").read_text())["properties"]["status"]["enum"]
    audit_types = set(
        json.loads((contracts / "audit-event.schema.json").read_text())["properties"]["type"]["enum"]
    )
    mapped = [action_event_type(status) for status in statuses]
    assert mapped == [f"action.{status}" for status in statuses]
    assert set(mapped) <= audit_types
