"""Each JSON Schema example persists and reads back as the same document."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection
from tests.schema_check import assert_matches_example_schema
from triage_db.repositories import (
    compose_case_bundle,
    get_action,
    get_alert,
    get_audit_event,
    get_bot_run,
    get_case,
    get_decision,
    get_evidence_pack,
    get_next_steps_pack,
    get_raw,
    save_action,
    save_alert,
    save_audit_event,
    save_bot_run_document,
    save_case,
    save_decision,
    save_evidence_pack,
    save_next_steps_pack,
    save_webhook_payload,
)

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"

# Longest prefix first so case-bundle matches before case.
_KINDS = (
    "audit-event",
    "bot-run",
    "case-bundle",
    "evidence-pack",
    "next-steps-pack",
    "splunk-webhook",
    "triage-decision",
    "action",
    "alert",
    "case",
)


def example_names(kind: str | None = None) -> list[str]:
    """Positive examples discovered from contracts/examples, not a frozen list."""
    paths = sorted(EXAMPLES.glob("*.json"))
    if kind is None:
        return [path.name for path in paths]
    return [path.name for path in paths if kind_of(path.name) == kind]


def kind_of(name: str) -> str:
    for kind in _KINDS:
        if name.startswith(kind + "."):
            return kind
    raise AssertionError(f"no persister for {name}")


def load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text())


def test_example_inventory_matches_contracts() -> None:
    discovered = example_names()
    assert discovered, "contracts/examples has no positive examples"
    assert {kind_of(name) for name in discovered} <= set(_KINDS)
    assert len(discovered) == len(set(discovered))


def test_schema_examples_round_trip(conn: Connection) -> None:
    for name in example_names("alert"):
        save_alert(conn, load(name))
    save_alert(
        conn,
        {
            "alert_id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            "source": {
                "system": "splunk",
                "instance": "splunk-onprem-sg1",
                "sid": "scheduler-unchanged-stub",
                "search_name": "Unchanged high stub",
            },
            "received_at": "2026-11-18T03:01:00Z",
            "splunk_severity": "high",
            "title": "Unchanged high stub",
            "entities": {},
            "dedup_key": "stub-unchanged-high",
            "raw": {"sid": "scheduler-unchanged-stub"},
        },
    )

    for name in example_names("triage-decision"):
        original = load(name)
        save_decision(conn, original)
        loaded = get_decision(conn, original["decision_id"])
        assert loaded == original
        assert_matches_example_schema(name, loaded)

    for name in example_names("alert"):
        original = load(name)
        loaded = get_alert(conn, original["alert_id"])
        assert loaded == original
        assert_matches_example_schema(name, loaded)
        row = conn.execute(
            text(
                """
                SELECT sid, search_name, title, splunk_severity, dedup_key
                FROM alerts WHERE alert_id = CAST(:alert_id AS uuid)
                """
            ),
            {"alert_id": original["alert_id"]},
        ).one()
        assert row.sid == original["source"]["sid"]
        assert row.search_name == original["source"]["search_name"]
        assert row.title == original["title"]
        assert row.splunk_severity == original["splunk_severity"]
        assert row.dedup_key == original["dedup_key"]
        outbox = conn.execute(
            text(
                """
                SELECT status, attempts FROM triage_outbox
                WHERE alert_id = CAST(:alert_id AS uuid)
                """
            ),
            {"alert_id": original["alert_id"]},
        ).one()
        assert outbox.status == "pending"
        assert outbox.attempts == 0

    for name in example_names("case"):
        original = load(name)
        save_case(conn, original)
        loaded = get_case(conn, original["case_id"])
        assert loaded == original
        assert_matches_example_schema(name, loaded)
        stored = conn.execute(
            text(
                """
                SELECT status, queue, priority, version, assignee
                FROM cases WHERE case_id = CAST(:case_id AS uuid)
                """
            ),
            {"case_id": original["case_id"]},
        ).one()
        assert stored.status == original["status"]
        assert stored.queue == original["queue"]
        assert stored.priority == original["priority"]
        assert stored.version == original["version"]
        assert stored.assignee == original["assignee"]

    escalated = load("case.escalated.json")
    closed = load("case.auto-closed.json")
    open_flag = conn.execute(
        text("SELECT case_open FROM alerts WHERE alert_id = CAST(:alert_id AS uuid)"),
        {"alert_id": escalated["alert_ids"][0]},
    ).scalar_one()
    closed_flag = conn.execute(
        text("SELECT case_open FROM alerts WHERE alert_id = CAST(:alert_id AS uuid)"),
        {"alert_id": closed["alert_ids"][0]},
    ).scalar_one()
    assert open_flag is True
    assert closed_flag is False

    for evidence_name in example_names("evidence-pack"):
        evidence = load(evidence_name)
        save_evidence_pack(conn, evidence)
        loaded_evidence = get_evidence_pack(conn, evidence["evidence_pack_id"])
        assert loaded_evidence == evidence
        assert_matches_example_schema(evidence_name, loaded_evidence)
        item_ids = conn.execute(
            text(
                """
                SELECT evidence_id FROM evidence_items
                WHERE evidence_pack_id = CAST(:pack_id AS uuid)
                ORDER BY position
                """
            ),
            {"pack_id": evidence["evidence_pack_id"]},
        ).scalars()
        assert list(item_ids) == [item["evidence_id"] for item in evidence["items"]]

    for steps_name in example_names("next-steps-pack"):
        steps = load(steps_name)
        save_next_steps_pack(conn, steps)
        loaded_steps = get_next_steps_pack(conn, steps["next_steps_pack_id"])
        assert loaded_steps == steps
        assert_matches_example_schema(steps_name, loaded_steps)
        stored_steps = conn.execute(
            text(
                """
                SELECT steps FROM next_steps_packs
                WHERE next_steps_pack_id = CAST(:pack_id AS uuid)
                """
            ),
            {"pack_id": steps["next_steps_pack_id"]},
        ).scalar_one()
        assert stored_steps == steps["steps"]

    for action_name in example_names("action"):
        action = load(action_name)
        save_action(conn, action)
        loaded_action = get_action(conn, action["action_id"])
        assert loaded_action == action
        assert_matches_example_schema(action_name, loaded_action)

    for name in example_names("audit-event"):
        original = load(name)
        save_audit_event(conn, original)
        loaded_event = get_audit_event(conn, original["event_id"])
        assert loaded_event == original
        assert_matches_example_schema(name, loaded_event)


def test_bot_run_examples_round_trip(conn: Connection) -> None:
    assert example_names("bot-run"), "bot-run examples must exist under contracts/examples"
    for name in example_names("bot-run"):
        original = load(name)
        save_bot_run_document(conn, original)
        loaded = get_bot_run(conn, original["run_id"])
        assert loaded == original
        assert_matches_example_schema(name, loaded)
        stored = conn.execute(
            text(
                """
                SELECT case_ids, trigger, proposals_made, enrichments_added
                FROM bot_runs WHERE run_id = CAST(:run_id AS uuid)
                """
            ),
            {"run_id": original["run_id"]},
        ).one()
        assert stored.case_ids == original.get("case_ids")
        assert stored.trigger == original.get("trigger")
        assert stored.proposals_made == original.get("proposals_made")
        assert stored.enrichments_added == original.get("enrichments_added")


def test_case_bundle_is_composed_from_stored_rows(conn: Connection) -> None:
    bundles = example_names("case-bundle")
    assert bundles, "case-bundle examples must exist under contracts/examples"
    for bundle_name in bundles:
        _compose_bundle_example(conn, bundle_name)


def _compose_bundle_example(conn: Connection, bundle_name: str) -> None:
    bundle = load(bundle_name)
    save_alert(conn, load("alert.escalate.json"))
    save_decision(conn, bundle["decision"])
    save_case(conn, bundle["case"])
    save_evidence_pack(conn, bundle["evidence_pack"])
    save_next_steps_pack(conn, bundle["next_steps_pack"])
    for action in bundle["proposed_actions"]:
        save_action(conn, action)
    composed = compose_case_bundle(
        conn, bundle["case"]["case_id"], generated_at=bundle["generated_at"]
    )
    assert composed == bundle
    assert_matches_example_schema(bundle_name, composed)


def test_splunk_webhook_examples_round_trip_as_alert_raw(conn: Connection) -> None:
    for name in example_names("splunk-webhook"):
        original = load(name)
        alert_id = save_webhook_payload(conn, original)
        loaded = get_raw(conn, alert_id)
        assert loaded == original
        assert_matches_example_schema(name, loaded)
