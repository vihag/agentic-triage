"""ADR-0005 combination order, routing table, labels, and guardrails."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from contracts.agent.interfaces import MockFuzzyMatcher
from jsonschema import Draft202012Validator

from triage_agent.agent import DefaultTriageAgent, plugin_certainties
from triage_agent.contract import (
    DefaultRoutingPolicy,
    FuzzyMatchResult,
    RuleResult,
    SeverityEffect,
    SimilarItem,
    TriageContext,
    combine_severity,
)
from triage_agent.engine import RuleEngine
from triage_agent.fuzzy.errors import FuzzyTimeout
from triage_agent.fuzzy.fallback import GUARDRAIL, FuzzyOutcome
from triage_agent.results import matched
from triage_agent.routing import (
    AUTO_CLOSE_SAMPLE_GUARDRAIL,
    NEVER_AUTO_CLOSE_GUARDRAIL,
    RoutingConfig,
    build_decision,
    in_auto_close_sample,
)
from triage_agent.rules.allow_011 import RULE as ALLOW_011
from triage_agent.rules.auth_003 import RULE as AUTH_003
from triage_agent.rules.priv_002 import RULE as PRIV_002
from triage_agent.version import __version__, agent_version

ALERT = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SAMPLED = "213ec2f0-20eb-4ef8-8b0e-ad33829bc825"
PUBLISHED_DOWNGRADE = "77777777-7777-4777-8777-777777777777"
DECISION_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
DECIDED_AT = "2026-11-18T04:00:00Z"
POLICY = DefaultRoutingPolicy()
CONFIG = RoutingConfig()


def rule(
    op: str,
    severity: str | None = None,
    delta: int = 0,
    *,
    matched: bool = True,
    rule_id: str = "RULE-1",
    labels: Sequence[str] = (),
    evidence: Sequence[str] = (),
) -> RuleResult:
    return RuleResult(
        rule_id,
        "1.0.0",
        matched,
        SeverityEffect(op, severity, delta),  # type: ignore[arg-type]
        "because",
        labels,
        evidence,
    )


def fuzzy(
    suggested: str,
    confidence: float,
    *,
    labels: Sequence[str] = (),
    similar: Sequence[SimilarItem] = (),
) -> FuzzyMatchResult:
    return FuzzyMatchResult(
        "mock-fuzzy",
        "mock",
        similar,
        suggested,  # type: ignore[arg-type]
        confidence,
        "fixture",
        labels,
    )


def decide(
    original: str,
    rules: Sequence[RuleResult] = (),
    match: FuzzyMatchResult | None = None,
    *,
    alert_id: str = ALERT,
    config: RoutingConfig = CONFIG,
    certainties: dict[str, float] | None = None,
) -> dict[str, Any]:
    if match is None:
        outcome = FuzzyOutcome(None, (GUARDRAIL,))
    else:
        outcome = FuzzyOutcome(match, ())
    return build_decision(
        {"alert_id": alert_id, "splunk_severity": original},
        rules,
        outcome,
        policy=POLICY,
        config=config,
        decision_id=DECISION_ID,
        decided_at=DECIDED_AT,
        latency_ms=0,
        certainties=certainties,
    )


def assert_valid(validator: Draft202012Validator, decision: dict[str, Any]) -> None:
    errors = list(validator.iter_errors(decision))
    assert errors == []


def test_combine_order_set_then_delta_then_one_fuzzy_step_then_clamps() -> None:
    """Contract order: start, set, delta, one fuzzy step, then floor and ceiling."""
    # The last matched set wins. An unmatched set is ignored. Delta applies after set.
    assert combine_severity(
        "critical",
        [rule("set", "low", rule_id="SET-A"), rule("set", "high", rule_id="SET-B")],
        None,
    ) == "high"
    assert combine_severity("low", [rule("set", "critical", matched=False)], None) == "low"
    assert combine_severity(
        "medium", [rule("set", "high"), rule("delta", delta=-1)], None
    ) == "medium"
    assert combine_severity(
        "informational", [rule("delta", delta=2), rule("delta", delta=2, rule_id="D2")], None
    ) == "critical"
    # One fuzzy level, and only when confidence is at least 0.75.
    assert combine_severity("medium", [], fuzzy("critical", 0.74)) == "medium"
    assert combine_severity("medium", [], fuzzy("critical", 0.75)) == "high"
    assert combine_severity("medium", [], fuzzy("critical", 0.99)) == "high"
    assert combine_severity("high", [], fuzzy("informational", 0.9)) == "medium"
    # Floor and ceiling run after the nudge, so a rule clamp beats the model.
    assert combine_severity(
        "high", [rule("floor", "high")], fuzzy("informational", 0.99)
    ) == "high"
    assert combine_severity("low", [rule("ceiling", "low")], fuzzy("critical", 0.99)) == "low"
    # The decision path calls that same function.
    assert decide("medium", [], fuzzy("critical", 0.99))["final_severity"] == "high"
    held = decide("high", [rule("floor", "high")], fuzzy("informational", 0.99))
    assert held["final_severity"] == "high"
    clamped = decide("low", [rule("ceiling", "low")], fuzzy("critical", 0.99))
    assert clamped["final_severity"] == "low"


def test_routing_table_matches_adr_0005(decision_validator: Draft202012Validator) -> None:
    escalated = decide("medium", [rule("floor", "high", labels=("candidate:tor-egress",))])
    assert escalated["direction"] == "escalated"
    assert escalated["disposition"] == "enqueue_for_triage"
    assert escalated["final_severity"] == "high"
    assert escalated["candidate_labels"] == [
        {"name": "candidate:tor-egress", "source": "rule", "confidence": 0.8}
    ]
    assert escalated["policy"]["guardrails_triggered"] == [GUARDRAIL]
    assert "Escalations always go to the human queue." in escalated["policy"]["rationale"]

    closed = decide(
        "high",
        [rule("ceiling", "low", rule_id=ALLOW_011.rule_id, labels=("benign:av-selftest",))],
        fuzzy("informational", 0.93),
        alert_id=PUBLISHED_DOWNGRADE,
        certainties={ALLOW_011.rule_id: ALLOW_011.certainty},
    )
    assert closed["direction"] == "downgraded"
    assert closed["disposition"] == "auto_closed"
    assert closed["confidence"] == 0.95
    assert closed["policy"]["guardrails_triggered"] == []
    assert closed["policy"]["rationale"] == (
        "Downgraded high->low with confidence 0.95 >= 0.85, "
        "no never_auto_close rule matched: auto-close with audit record."
    )

    quiet = decide(
        "high",
        [rule("ceiling", "low")],
        fuzzy("informational", 0.2),
        config=RoutingConfig(sample_rate=0),
    )
    assert quiet["disposition"] == "enqueue_downgrade_review"
    assert quiet["policy"]["rationale"] == (
        "Downgraded high->low with confidence 0.5 < 0.85: enqueue for downgrade review."
    )

    guarded = decide(
        "high",
        [rule("ceiling", "low"), rule("never_auto_close", rule_id="CROWN")],
        fuzzy("informational", 0.93),
        config=RoutingConfig(sample_rate=0),
    )
    assert guarded["disposition"] == "enqueue_downgrade_review"
    assert NEVER_AUTO_CLOSE_GUARDRAIL in guarded["policy"]["guardrails_triggered"]
    assert "never_auto_close matched" in guarded["policy"]["rationale"]

    timed_out = decide("high", [rule("ceiling", "low", rule_id="ALLOW-011-eicar-on-ci")])
    assert timed_out["fuzzy_result"] is None
    assert timed_out["disposition"] == "enqueue_downgrade_review"
    assert timed_out["policy"]["guardrails_triggered"] == [GUARDRAIL]
    assert timed_out["rule_severity"] == "low"
    assert "fuzzy matcher timed out" in timed_out["policy"]["rationale"]

    both = decide(
        "high",
        [rule("ceiling", "low"), rule("never_auto_close", rule_id="CROWN")],
    )
    assert both["policy"]["guardrails_triggered"] == [GUARDRAIL, NEVER_AUTO_CLOSE_GUARDRAIL]
    assert "fuzzy matcher timed out and never_auto_close matched" in both["policy"]["rationale"]

    unchanged_high = decide("high", [], fuzzy("high", 0.4))
    assert unchanged_high["direction"] == "unchanged"
    assert unchanged_high["disposition"] == "enqueue_for_triage"
    assert unchanged_high["candidate_labels"] == []
    assert unchanged_high["confidence"] == 0.4
    assert unchanged_high["policy"]["rationale"] == (
        "Unchanged at high: pass through to the human queue at standard priority "
        "(no candidate label)."
    )

    labeled = decide(
        "high",
        [rule("floor", "high", labels=("candidate:tor-egress",))],
        fuzzy("high", 0.4),
    )
    assert labeled["direction"] == "unchanged"
    assert labeled["candidate_labels"] == []

    recorded = decide("low", [], fuzzy("low", 0.4))
    assert recorded["disposition"] == "recorded_only"
    assert recorded["policy"]["rationale"] == "Unchanged at low: recorded only."

    for decision in (
        escalated,
        closed,
        quiet,
        guarded,
        timed_out,
        both,
        unchanged_high,
        labeled,
        recorded,
    ):
        assert decision["agent_version"] == agent_version() == f"triage-agent/{__version__}"
        assert_valid(decision_validator, decision)


def test_auto_close_threshold_is_inclusive(decision_validator: Draft202012Validator) -> None:
    closed = decide(
        "high",
        [rule("ceiling", "low")],
        fuzzy("low", 0.9),
        config=RoutingConfig(sample_rate=0),
    )
    assert closed["confidence"] == 0.85
    assert closed["disposition"] == "auto_closed"
    assert "0.85 >= 0.85" in closed["policy"]["rationale"]
    assert_valid(decision_validator, closed)


def test_five_percent_sample_sends_auto_closes_to_review(
    decision_validator: Draft202012Validator,
) -> None:
    rules = [rule("ceiling", "low", rule_id=ALLOW_011.rule_id)]
    match = fuzzy("informational", 0.93)
    published_certainty = {ALLOW_011.rule_id: ALLOW_011.certainty}
    published = decide(
        "high", rules, match, alert_id=PUBLISHED_DOWNGRADE, certainties=published_certainty
    )
    sampled = decide("high", rules, match, alert_id=SAMPLED, certainties=published_certainty)
    forced = decide(
        "high",
        rules,
        match,
        alert_id=PUBLISHED_DOWNGRADE,
        config=RoutingConfig(sample_rate=1),
        certainties=published_certainty,
    )
    disabled = decide(
        "high",
        rules,
        match,
        alert_id=SAMPLED,
        config=RoutingConfig(sample_rate=0),
        certainties=published_certainty,
    )
    assert published["disposition"] == "auto_closed"
    assert sampled["disposition"] == "enqueue_downgrade_review"
    assert sampled["policy"]["guardrails_triggered"] == [AUTO_CLOSE_SAMPLE_GUARDRAIL]
    assert "5% downgrade-review sample" in sampled["policy"]["rationale"]
    assert forced["disposition"] == "enqueue_downgrade_review"
    assert "100% downgrade-review sample" in forced["policy"]["rationale"]
    assert disabled["disposition"] == "auto_closed"
    assert_valid(decision_validator, sampled)


def test_fuzzy_clause_and_label_confidence_bounds(
    decision_validator: Draft202012Validator,
) -> None:
    agrees = decide(
        "low",
        [rule("delta", delta=1, labels=("guard:privileged-user", "guard:privileged-user"))],
        fuzzy("critical", 1.0, labels=("candidate:account-takeover",)),
    )
    assert agrees["final_severity"] == "high"
    assert agrees["rule_severity"] == "medium"
    assert "rule delta=+1, fuzzy agrees (1 >= 0.75)" in agrees["policy"]["rationale"]
    assert agrees["candidate_labels"] == [
        {"name": "guard:privileged-user", "source": "rule", "confidence": 0.8},
        {"name": "candidate:account-takeover", "source": "fuzzy", "confidence": 1.0},
    ]

    disagrees = decide(
        "low",
        [rule("set", "critical"), rule("ceiling", "high")],
        fuzzy("informational", 0.9),
    )
    assert disagrees["final_severity"] == "high"
    assert "rule set=critical, rule ceiling=high" in disagrees["policy"]["rationale"]
    assert "fuzzy suggests informational (0.9 >= 0.75)" in disagrees["policy"]["rationale"]

    below = decide(
        "medium",
        [
            rule(
                "floor",
                "high",
                rule_id="AUTH-003-fail-then-success-external",
                labels=("candidate:credential-stuffing",),
            )
        ],
        fuzzy(
            "low",
            0.1,
            labels=("candidate:account-takeover", "candidate:account-takeover"),
        ),
    )
    assert below["final_severity"] == "high"
    assert "fuzzy confidence 0.1 < 0.75" in below["policy"]["rationale"]
    assert below["candidate_labels"][1]["confidence"] == 0.1
    assert_valid(decision_validator, agrees)
    assert_valid(decision_validator, below)


def test_inert_effects_do_not_explain_an_escalation() -> None:
    decision = decide(
        "low",
        [
            rule("delta", delta=1, rule_id="PRIV"),
            rule("floor", None, rule_id="BARE"),
            rule("none", rule_id="NONE"),
            rule("never_auto_close", rule_id="CROWN"),
        ],
    )
    assert decision["final_severity"] == "medium"
    assert decision["policy"]["rationale"] == (
        "Escalated low->medium: rule delta=+1. Escalations always go to the human queue."
    )
    assert decision["policy"]["guardrails_triggered"] == [GUARDRAIL, NEVER_AUTO_CLOSE_GUARDRAIL]
    assert decision["rule_results"][0]["effect"] == {"op": "delta", "delta": 1}
    bare = next(row for row in decision["rule_results"] if row["rule_id"] == "BARE")
    assert bare["effect"] == {"op": "floor"}


def test_two_rule_certainties_are_averaged_before_the_fuzzy_mix() -> None:
    decision = decide(
        "low",
        [
            rule("floor", "high", rule_id=AUTH_003.rule_id),
            rule("delta", delta=1, rule_id=PRIV_002.rule_id),
        ],
        certainties={
            AUTH_003.rule_id: AUTH_003.certainty,
            PRIV_002.rule_id: PRIV_002.certainty,
        },
    )
    assert decision["final_severity"] == "high"
    assert decision["confidence"] == 0.85


def test_downgrade_just_below_the_gate_goes_to_review() -> None:
    decision = decide(
        "high",
        [rule("ceiling", "low")],
        fuzzy("low", 0.88),
        config=RoutingConfig(sample_rate=0),
    )
    assert decision["confidence"] == 0.84
    assert decision["disposition"] == "enqueue_downgrade_review"
    assert "0.84 < 0.85" in decision["policy"]["rationale"]


def test_unchanged_medium_is_queued() -> None:
    decision = decide("medium", [], fuzzy("medium", 0.4))
    assert decision["final_severity"] == "medium"
    assert decision["direction"] == "unchanged"
    assert decision["disposition"] == "enqueue_for_triage"
    assert decision["candidate_labels"] == []


def test_auto_close_sample_is_about_five_percent() -> None:
    ids = [f"alert-{index:05d}" for index in range(10_000)]
    hits = sum(in_auto_close_sample(alert_id, 0.05) for alert_id in ids)
    assert 400 <= hits <= 600


def test_fuzzy_only_nudge_is_one_level_and_copies_its_label() -> None:
    item = SimilarItem("known_pattern", "PAT-01", 0.5, "pattern")
    decision = decide(
        "medium",
        [],
        fuzzy("critical", 0.8, labels=("candidate:account-takeover",), similar=(item,)),
    )
    assert decision["rule_severity"] == "medium"
    assert decision["final_severity"] == "high"
    assert decision["confidence"] == 0.8
    assert decision["candidate_labels"] == [
        {"name": "candidate:account-takeover", "source": "fuzzy", "confidence": 0.8}
    ]
    assert "verified_severity" not in decision["fuzzy_result"]["similar_items"][0]
    assert decision["fuzzy_result"]["similar_items"][0]["verdict"] == "unknown"


def test_config_version_and_fuzzy_threshold_are_honoured() -> None:
    held = decide(
        "medium",
        [],
        fuzzy("high", 0.8),
        config=RoutingConfig(version="test-version", fuzzy_min_confidence=0.9, sample_rate=0),
    )
    assert held["final_severity"] == "medium"
    assert held["policy"]["policy_id"] == "severity-routing"
    assert held["policy"]["version"] == "test-version"


def test_matched_rules_lead_the_explanation() -> None:
    decision = decide(
        "low",
        [
            rule("none", matched=False, rule_id="EARLY"),
            rule("delta", delta=1, rule_id="LATE"),
        ],
    )
    assert [row["rule_id"] for row in decision["rule_results"]] == ["LATE", "EARLY"]


def test_validate_alert_rejects_bad_fields() -> None:
    with pytest.raises(ValueError, match="alert_id"):
        decide("low", alert_id="")
    with pytest.raises(ValueError, match="alert_id"):
        build_decision(
            {"splunk_severity": "low"},
            [],
            FuzzyOutcome(None, (GUARDRAIL,)),
            policy=POLICY,
            config=CONFIG,
            decision_id=DECISION_ID,
            decided_at=DECIDED_AT,
            latency_ms=0,
        )
    with pytest.raises(ValueError, match="splunk_severity"):
        decide("severe")
    with pytest.raises(ValueError, match="splunk_severity"):
        build_decision(
            {"alert_id": ALERT, "splunk_severity": 4},
            [],
            FuzzyOutcome(None, (GUARDRAIL,)),
            policy=POLICY,
            config=CONFIG,
            decision_id=DECISION_ID,
            decided_at=DECIDED_AT,
            latency_ms=0,
        )


class SpyMatcher:
    matcher_id = "spy"

    def __init__(self, payload: FuzzyMatchResult | None = None, *, boom: bool = False) -> None:
        self.payload = payload
        self.boom = boom
        self.calls = 0
        self.kwargs: list[dict[str, Any]] = []

    def match(
        self, alert: Mapping[str, Any], k: int = 5, timeout_s: float = 5.0
    ) -> FuzzyMatchResult:
        self.calls += 1
        self.kwargs.append({"k": k, "timeout_s": timeout_s})
        if self.boom:
            raise FuzzyTimeout("fuzzy matcher timed out")
        if self.payload is not None:
            return self.payload
        return fuzzy(str(alert["splunk_severity"]), 0.5)


class _SoftCeiling:
    rule_id = "SOFT-1"
    version = "1.0.0"
    priority = 1
    certainty = 0.4

    def applies_to(self, alert: object) -> bool:
        return True

    def evaluate(self, alert: object, ctx: object) -> RuleResult:
        return matched(
            self.rule_id,
            self.version,
            SeverityEffect("ceiling", "low"),
            "soft ceiling",
            labels=("benign:soft",),
        )


class _NoCertainty:
    rule_id = "PLAIN-1"
    version = "1.0.0"
    priority = 2

    def applies_to(self, alert: object) -> bool:
        return False

    def evaluate(self, alert: object, ctx: object) -> RuleResult:
        return matched(self.rule_id, self.version, SeverityEffect("none"), "unused")


def test_agent_reads_certainty_from_the_rule() -> None:
    agent = DefaultTriageAgent(
        SpyMatcher(fuzzy("informational", 1.0)),
        engine=RuleEngine([_SoftCeiling(), _NoCertainty()]),
        config=RoutingConfig(sample_rate=0),
        clock=lambda: datetime(2026, 11, 18, 4, 0, tzinfo=UTC),
        monotonic=lambda: 0.0,
        new_id=lambda: DECISION_ID,
    )
    assert plugin_certainties(agent.engine.rules) == {"SOFT-1": 0.4}
    decision = agent.triage(
        {"alert_id": ALERT, "splunk_severity": "high"},
        TriageContext(),
    )
    assert decision["confidence"] == 0.7
    assert decision["disposition"] == "enqueue_downgrade_review"
    assert decision["candidate_labels"] == [
        {"name": "benign:soft", "source": "rule", "confidence": 0.4}
    ]


def test_agent_validates_before_calling_the_matcher() -> None:
    spy = SpyMatcher()
    agent = DefaultTriageAgent(spy)
    with pytest.raises(TypeError, match="mapping"):
        agent.triage(["nope"], TriageContext())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="TriageContext"):
        agent.triage({"alert_id": ALERT, "splunk_severity": "low"}, object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="splunk_severity"):
        agent.triage({"alert_id": ALERT}, TriageContext())
    assert spy.calls == 0


def test_agent_forwards_k_and_timeout_and_measures_latency(
    decision_validator: Draft202012Validator,
) -> None:
    spy = SpyMatcher()
    clock = datetime(2026, 11, 18, 4, 0, tzinfo=UTC)
    samples = iter((0.0, 2.0))
    agent = DefaultTriageAgent(
        spy,
        engine=RuleEngine([]),
        clock=lambda: clock,
        monotonic=lambda: next(samples),
        new_id=lambda: DECISION_ID,
        k=3,
        timeout_s=1.5,
        policy=POLICY,
        config=CONFIG,
    )
    decision = agent.triage({"alert_id": ALERT, "splunk_severity": "medium"}, TriageContext())
    assert spy.kwargs == [{"k": 3, "timeout_s": 1.5}]
    assert decision["latency_ms"] == 2000
    assert decision["decided_at"] == "2026-11-18T04:00:00Z"
    assert decision["disposition"] == "enqueue_for_triage"
    assert_valid(decision_validator, decision)

    naive = DefaultTriageAgent(
        SpyMatcher(),
        engine=RuleEngine([]),
        clock=lambda: datetime(2026, 11, 18, 4, 0),
        monotonic=lambda: 0.0,
        new_id=lambda: DECISION_ID,
    )
    assert naive.triage(
        {"alert_id": ALERT, "splunk_severity": "low"}, TriageContext()
    )["decided_at"] == "2026-11-18T04:00:00Z"

    offset = timezone(timedelta(hours=2))
    backwards = iter((5.0, 1.0))
    shifted = DefaultTriageAgent(
        SpyMatcher(boom=True),
        engine=RuleEngine([]),
        clock=lambda: datetime(2026, 11, 18, 6, 0, tzinfo=offset),
        monotonic=lambda: next(backwards),
        new_id=lambda: DECISION_ID,
    )
    timed = shifted.triage({"alert_id": ALERT, "splunk_severity": "low"}, TriageContext())
    assert timed["decided_at"] == "2026-11-18T04:00:00Z"
    assert timed["fuzzy_result"] is None
    assert timed["latency_ms"] == 0
    assert timed["disposition"] == "recorded_only"
    assert timed["policy"]["guardrails_triggered"] == [GUARDRAIL]
    assert_valid(decision_validator, timed)


def test_default_agent_uses_a_mock_matcher_and_real_ids(
    decision_validator: Draft202012Validator,
) -> None:
    matcher = MockFuzzyMatcher()
    agent = DefaultTriageAgent(matcher)
    decision = agent.triage(
        {
            "alert_id": ALERT,
            "splunk_severity": "medium",
            "title": "Scheduled heartbeat",
            "source": {"search_name": "Heartbeat"},
        },
        TriageContext(),
    )
    assert_valid(decision_validator, decision)
    assert decision["decision_id"] != DECISION_ID
    assert decision["final_severity"] == "medium"
    assert decision["fuzzy_result"]["model"] == "mock"
    assert len(decision["rule_results"]) == len(agent.engine.rules)
