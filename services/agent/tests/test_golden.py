"""Golden alerts match the published TriageDecision examples.

Ids and timestamps differ per run. Measured latency does too. The published
examples list the rules that explain the case; the starter set also records
every other rule, and those extra rows do not change the decision.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from contracts.agent.interfaces import MockFuzzyMatcher
from jsonschema import Draft202012Validator

from triage_agent.agent import DefaultTriageAgent
from triage_agent.contract import (
    FuzzyMatchResult,
    RulePlugin,
    SimilarItem,
    TriageContext,
)
from triage_agent.engine import RuleEngine
from triage_agent.fuzzy.errors import FuzzyTimeout
from triage_agent.rules.allow_007 import RULE as ALLOW_007
from triage_agent.rules.allow_011 import RULE as ALLOW_011
from triage_agent.rules.auth_003 import RULE as AUTH_003
from triage_agent.rules.crown_001 import RULE as CROWN_001

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "contracts" / "examples"
AGENT_SRC = Path(__file__).resolve().parents[1] / "src" / "triage_agent"
DECISION_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
WHEN = datetime(2026, 11, 18, 4, 0, tzinfo=UTC)
GENERATED = {"decision_id", "decided_at", "case_id", "latency_ms"}
FORBIDDEN = {"openai", "requests", "httpx", "urllib", "socket", "anthropic"}


def load_example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text())


def without_generated(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in GENERATED}


CONFIDENCE_TOLERANCE = 0.05


def assert_matches_example(
    decision: dict[str, Any], example: dict[str, Any], *, project_rules: bool
) -> None:
    """Severities, direction, disposition, and label names. Confidence within tolerance.

    The escalate example's fuzzy label is 0.78 while the matcher confidence is
    0.82. Label confidence is the fuzzy confidence, so that one field is not exact.
    """
    body = without_generated(decision)
    expected = without_generated(example)
    if project_rules:
        by_id = {row["rule_id"]: row for row in body["rule_results"]}
        body["rule_results"] = [by_id[row["rule_id"]] for row in expected["rule_results"]]
    got_labels = body.pop("candidate_labels")
    exp_labels = expected.pop("candidate_labels")
    assert abs(body.pop("confidence") - expected.pop("confidence")) <= CONFIDENCE_TOLERANCE
    assert [(item["name"], item["source"]) for item in got_labels] == [
        (item["name"], item["source"]) for item in exp_labels
    ]
    for got, exp in zip(got_labels, exp_labels, strict=True):
        assert abs(got["confidence"] - exp["confidence"]) <= CONFIDENCE_TOLERANCE
    assert body == expected


def fuzzy_from(payload: dict[str, Any]) -> FuzzyMatchResult:
    items = tuple(
        SimilarItem(
            item["ref_type"],
            item["ref_id"],
            item["similarity"],
            item["summary"],
            item.get("verified_severity"),
            item.get("verdict", "unknown"),
        )
        for item in payload["similar_items"]
    )
    return FuzzyMatchResult(
        payload["matcher_id"],
        payload["model"],
        items,
        payload["suggested_severity"],
        payload["confidence"],
        payload["rationale"],
        tuple(payload.get("suggested_labels") or ()),
    )


class TimeoutMatcher:
    """CI stub. Raises before any model call."""

    matcher_id = "timeout-mock"

    def match(
        self, alert: Mapping[str, Any], k: int = 5, timeout_s: float = 5.0
    ) -> FuzzyMatchResult:
        raise FuzzyTimeout("fuzzy matcher timed out")


def agent_for(matcher: object, rules: Sequence[RulePlugin] | None) -> DefaultTriageAgent:
    engine = None if rules is None else RuleEngine(list(rules))
    return DefaultTriageAgent(
        matcher,  # type: ignore[arg-type]
        engine=engine,
        clock=lambda: WHEN,
        monotonic=lambda: 0.0,
        new_id=lambda: DECISION_ID,
    )


def assert_valid(validator: Draft202012Validator, decision: dict[str, Any]) -> None:
    errors = list(validator.iter_errors(decision))
    assert errors == []


def test_example_rule_sets_match_the_published_decisions(
    escalate_alert: dict[str, Any],
    downgrade_alert: dict[str, Any],
    ci_context: TriageContext,
    decision_validator: Draft202012Validator,
) -> None:
    escalate = load_example("triage-decision.escalate.json")
    downgrade = load_example("triage-decision.downgrade.json")
    unchanged = load_example("triage-decision.unchanged.json")
    escalate_agent = agent_for(
        MockFuzzyMatcher(
            {"Excessive Failed Logins Followed By Success": fuzzy_from(escalate["fuzzy_result"])}
        ),
        [AUTH_003, ALLOW_007],
    )
    downgrade_agent = agent_for(
        MockFuzzyMatcher(
            {"Malware Signature Detected On Endpoint": fuzzy_from(downgrade["fuzzy_result"])}
        ),
        [ALLOW_011, CROWN_001],
    )
    unchanged_agent = agent_for(TimeoutMatcher(), [])
    unchanged_alert = {
        "alert_id": unchanged["alert_id"],
        "splunk_severity": "high",
        "title": "Scheduled heartbeat",
        "source": {"search_name": "Unchanged High"},
    }

    cases = [
        (escalate_agent, escalate_alert, TriageContext(), escalate),
        (downgrade_agent, downgrade_alert, ci_context, downgrade),
        (unchanged_agent, unchanged_alert, TriageContext(), unchanged),
    ]
    for built, alert, ctx, example in cases:
        decision = built.triage(alert, ctx)
        assert_valid(decision_validator, decision)
        assert decision["decision_id"] != example["decision_id"]
        assert "case_id" not in decision
        assert "latency_ms" in decision
        assert_matches_example(decision, example, project_rules=False)


def test_starter_rules_keep_the_example_outcome(
    engine: RuleEngine,
    escalate_alert: dict[str, Any],
    downgrade_alert: dict[str, Any],
    ci_context: TriageContext,
    decision_validator: Draft202012Validator,
) -> None:
    escalate = load_example("triage-decision.escalate.json")
    downgrade = load_example("triage-decision.downgrade.json")
    unchanged = load_example("triage-decision.unchanged.json")
    fixtures = {
        "Excessive Failed Logins Followed By Success": fuzzy_from(escalate["fuzzy_result"]),
        "Malware Signature Detected On Endpoint": fuzzy_from(downgrade["fuzzy_result"]),
    }
    mocked = agent_for(MockFuzzyMatcher(fixtures), None)
    timed = agent_for(TimeoutMatcher(), None)
    unchanged_alert = {
        "alert_id": unchanged["alert_id"],
        "splunk_severity": "high",
        "title": "Scheduled heartbeat",
        "source": {"search_name": "Unchanged High"},
    }
    # The fixture engine is the discovered starter set. These agents discover too.
    assert [rule.rule_id for rule in mocked.engine.rules] == [rule.rule_id for rule in engine.rules]

    produced = [
        (mocked, escalate_alert, TriageContext(), escalate),
        (mocked, downgrade_alert, ci_context, downgrade),
        (timed, unchanged_alert, TriageContext(), unchanged),
    ]
    for built, alert, ctx, example in produced:
        decision = built.triage(alert, ctx)
        assert_valid(decision_validator, decision)
        assert {row["rule_id"] for row in decision["rule_results"]} == {
            rule.rule_id for rule in built.engine.rules
        }
        assert_matches_example(decision, example, project_rules=True)
        if example["direction"] == "escalated":
            assert [label["name"] for label in decision["candidate_labels"]] == [
                "candidate:credential-stuffing",
                "candidate:account-takeover",
            ]
            fuzzy_label = next(
                label for label in decision["candidate_labels"] if label["source"] == "fuzzy"
            )
            assert fuzzy_label["confidence"] == example["fuzzy_result"]["confidence"]


def test_routing_modules_do_not_call_a_model() -> None:
    for path in (AGENT_SRC / "agent.py", AGENT_SRC / "routing.py", AGENT_SRC / "version.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".", 1)[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {(node.module or "").split(".", 1)[0]}
            else:
                names = set()
            assert names.isdisjoint(FORBIDDEN)
            if isinstance(node, ast.Attribute) and node.attr == "complete_json":
                raise AssertionError(f"{path.name} calls complete_json")
            if isinstance(node, ast.Name) and node.id == "PgvectorFuzzyMatcher":
                raise AssertionError(f"{path.name} names PgvectorFuzzyMatcher")
