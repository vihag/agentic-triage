"""Starter rules reproduce the contract examples and the ADR-0005 combination."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from triage_agent.contract import (
    DefaultRoutingPolicy,
    FuzzyMatchResult,
    RuleResult,
    TriageContext,
    combine_severity,
)
from triage_agent.engine import RuleEngine

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "contracts" / "examples"
SCHEMAS = REPO / "contracts" / "schemas"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text())


def _schema_dict(result: RuleResult) -> dict:
    effect: dict[str, object] = {"op": result.effect.op}
    if result.effect.severity is not None:
        effect["severity"] = result.effect.severity
    if result.effect.op == "delta":
        effect["delta"] = result.effect.delta
    body: dict[str, object] = {
        "rule_id": result.rule_id,
        "rule_version": result.rule_version,
        "matched": result.matched,
        "effect": effect,
        "rationale": result.rationale,
    }
    if result.labels:
        body["labels"] = list(result.labels)
    if result.evidence_refs:
        body["evidence_refs"] = list(result.evidence_refs)
    return body


def _validator() -> Draft202012Validator:
    registry: Registry = Registry()
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        contents = json.loads(path.read_text())
        resource = Resource.from_contents(contents, default_specification=DRAFT202012)
        registry = registry.with_resource(path.name, resource)
    return Draft202012Validator(
        {"$ref": "triage-decision.schema.json#/$defs/RuleResult"},
        registry=registry,
    )


def _by_id(results: list[RuleResult]) -> dict[str, RuleResult]:
    return {result.rule_id: result for result in results}


def test_every_discovered_rule_is_recorded(engine: RuleEngine, escalate_alert: dict) -> None:
    results = engine.run(escalate_alert, TriageContext())
    assert [result.rule_id for result in results] == [rule.rule_id for rule in engine.rules]
    assert len(results) == 6
    assert any(result.matched for result in results)
    assert any(not result.matched for result in results)


def test_escalate_example_rules(engine: RuleEngine, escalate_alert: dict) -> None:
    decision = load_example("triage-decision.escalate.json")
    found = _by_id(engine.run(escalate_alert, TriageContext()))
    expected = {row["rule_id"]: row for row in decision["rule_results"]}
    assert _schema_dict(found["AUTH-003-fail-then-success-external"]) == expected[
        "AUTH-003-fail-then-success-external"
    ]
    assert _schema_dict(found["ALLOW-007-known-scanner"]) == expected["ALLOW-007-known-scanner"]
    fuzzy = FuzzyMatchResult(
        "pgvector-knn+llm-judge",
        "mock",
        (),
        "high",
        0.82,
        "Agrees with the floor.",
    )
    assert combine_severity("medium", list(found.values()), fuzzy) == "high"


def test_downgrade_example_rules(
    engine: RuleEngine, downgrade_alert: dict, ci_context: TriageContext
) -> None:
    decision = load_example("triage-decision.downgrade.json")
    found = _by_id(engine.run(downgrade_alert, ci_context))
    expected = {row["rule_id"]: row for row in decision["rule_results"]}
    assert _schema_dict(found["ALLOW-011-eicar-on-ci"]) == expected["ALLOW-011-eicar-on-ci"]
    assert _schema_dict(found["CROWN-001-crown-jewel-asset"]) == expected[
        "CROWN-001-crown-jewel-asset"
    ]
    fuzzy = FuzzyMatchResult("mock-fuzzy", "mock", (), "informational", 0.93, "AV self-test.")
    final = combine_severity("high", list(found.values()), fuzzy)
    assert final == "low"
    never = any(
        result.matched and result.effect.op == "never_auto_close" for result in found.values()
    )
    disposition = DefaultRoutingPolicy().route("high", final, 0.95, never_auto_close=never)
    assert disposition == "auto_closed"


def test_crown_jewel_blocks_auto_close(engine: RuleEngine, downgrade_alert: dict) -> None:
    ctx = TriageContext(
        asset_inventory={"build-agent-07": {"crown_jewel": True, "group": "ci-build-agents"}}
    )
    results = engine.run(downgrade_alert, ctx)
    never = any(result.matched and result.effect.op == "never_auto_close" for result in results)
    final = combine_severity(
        "high",
        results,
        FuzzyMatchResult("mock-fuzzy", "mock", (), "informational", 0.93, "AV self-test."),
    )
    assert final == "low"
    assert (
        DefaultRoutingPolicy().route("high", final, 0.95, never_auto_close=never)
        == "enqueue_downgrade_review"
    )


def test_privileged_user_and_tor_and_scanner_move_severity(engine: RuleEngine) -> None:
    privileged = engine.run(
        {"entities": {"users": ["root"]}},
        TriageContext(identity_directory={"root": {"privileged": True}}),
    )
    assert combine_severity("low", privileged, None) == "medium"
    tor = engine.run({"title": "TOR egress detected"}, TriageContext())
    assert combine_severity("low", tor, None) == "high"
    scanner = engine.run(
        {"entities": {"src_ips": ["10.8.1.4"]}},
        TriageContext(allow_lists={"scanners": ["10.8.0.0/16"]}),
    )
    assert combine_severity("high", scanner, None) == "low"


def test_results_validate_against_the_rule_result_schema(
    engine: RuleEngine, escalate_alert: dict, downgrade_alert: dict, ci_context: TriageContext
) -> None:
    validator = _validator()
    batches = [
        engine.run(escalate_alert, TriageContext()),
        engine.run(downgrade_alert, ci_context),
        engine.run({"title": "port scan"}, TriageContext()),
    ]
    for batch in batches:
        assert len(batch) == 6
        for result in batch:
            errors = list(validator.iter_errors(_schema_dict(result)))
            assert errors == []

