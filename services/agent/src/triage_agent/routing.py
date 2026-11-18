"""Severity combination and the ADR-0005 routing table, as a TriageDecision.

``combine_severity`` and ``DefaultRoutingPolicy`` live in the contract. This
module calls them so a decision cannot drift from the contract gate. Decision
confidence is the implementation detail ADR-0005 leaves open: the mean of the
matched severity-rule certainties and the fuzzy confidence when both exist.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Never, cast

from triage_agent.contract import (
    SEVERITY_ORDER,
    FuzzyMatchResult,
    RoutingPolicy,
    RuleResult,
    Severity,
    SeverityEffect,
    SimilarItem,
    combine_severity,
    rank,
)
from triage_agent.fuzzy.fallback import GUARDRAIL, FuzzyOutcome
from triage_agent.version import agent_version

Direction = Literal["escalated", "downgraded", "unchanged"]
LabelSource = Literal["rule", "fuzzy", "llm", "analyst"]

# Used when a matched rule did not declare ``certainty``. The value itself
# lives on the rule plugin.
DEFAULT_RULE_CERTAINTY = 0.8
BASELINE_CONFIDENCE = 0.7
NEVER_AUTO_CLOSE_GUARDRAIL = "never_auto_close"
AUTO_CLOSE_SAMPLE_GUARDRAIL = "auto_close_sample"
_SEVERITY_OPS = frozenset({"floor", "ceiling", "set", "delta"})


@dataclass(frozen=True)
class RoutingConfig:
    """Thresholds versioned onto the decision as ``policy.version`` (ADR-0005)."""

    policy_id: str = "severity-routing"
    version: str = "2026-11-18"
    fuzzy_min_confidence: float = 0.75
    auto_close_min_confidence: float = 0.85
    sample_rate: float = 0.05


def direction_of(original: Severity, final: Severity) -> Direction:
    if rank(final) > rank(original):
        return "escalated"
    if rank(final) < rank(original):
        return "downgraded"
    return "unchanged"


def explanation_order(rules: Sequence[RuleResult]) -> list[RuleResult]:
    """Matches first, then misses. Each group keeps engine priority order.

    The engine still runs in ascending priority. The published examples lead
    with the rule that fired.
    """
    matched = [rule for rule in rules if rule.matched]
    missed = [rule for rule in rules if not rule.matched]
    return matched + missed


def decision_confidence(
    rules: Sequence[RuleResult],
    fuzzy: FuzzyMatchResult | None,
    certainties: Mapping[str, float],
) -> float:
    values = [
        certainties.get(rule.rule_id, DEFAULT_RULE_CERTAINTY)
        for rule in rules
        if rule.matched and rule.effect.op in _SEVERITY_OPS
    ]
    if values and fuzzy is not None:
        rule_certainty = sum(values) / len(values)
        return _units((rule_certainty + fuzzy.confidence) / 2)
    if values:
        return _units(sum(values) / len(values))
    if fuzzy is not None:
        return _units(fuzzy.confidence)
    return BASELINE_CONFIDENCE


def in_auto_close_sample(alert_id: str, rate: float) -> bool:
    """Stable 5% sample of auto-closes for downgrade-review drift monitoring."""
    if rate <= 0:
        return False
    if rate >= 1:
        return True
    digest = hashlib.sha256(alert_id.encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") / 2**64
    return bucket < rate


def build_decision(
    alert: Mapping[str, Any],
    rules: Sequence[RuleResult],
    outcome: FuzzyOutcome,
    *,
    policy: RoutingPolicy,
    config: RoutingConfig,
    decision_id: str,
    decided_at: str,
    latency_ms: int,
    certainties: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """One TriageDecision. ``contracts/`` shapes the body; this fills it."""
    alert_id, original = validate_alert(alert)
    fuzzy = None if outcome.result is None else outcome.result
    ordered = explanation_order(rules)
    known = dict(certainties or {})
    rule_severity = combine_severity(original, ordered, None, config.fuzzy_min_confidence)
    final = combine_severity(original, ordered, fuzzy, config.fuzzy_min_confidence)
    confidence = decision_confidence(ordered, fuzzy, known)
    direction = direction_of(original, final)
    guardrails = _guardrails(ordered, fuzzy is None)
    never_auto_close = bool(guardrails)
    disposition = policy.route(
        original, final, confidence, never_auto_close=never_auto_close
    )
    if disposition == "auto_closed" and in_auto_close_sample(alert_id, config.sample_rate):
        disposition = "enqueue_downgrade_review"
        guardrails.append(AUTO_CLOSE_SAMPLE_GUARDRAIL)
    body: dict[str, Any] = {
        "decision_id": decision_id,
        "alert_id": alert_id,
        "decided_at": decided_at,
        "agent_version": agent_version(),
        "original_severity": original,
        "rule_severity": rule_severity,
        "final_severity": final,
        "direction": direction,
        "disposition": disposition,
        "confidence": confidence,
        "candidate_labels": _candidate_labels(direction, ordered, fuzzy, known),
        "rule_results": [_rule_payload(rule) for rule in ordered],
        "fuzzy_result": None if fuzzy is None else _fuzzy_payload(fuzzy),
        "policy": {
            "policy_id": config.policy_id,
            "version": config.version,
            "rationale": _rationale(
                direction,
                disposition,
                original,
                final,
                confidence,
                ordered,
                fuzzy,
                guardrails,
                config,
            ),
            "guardrails_triggered": list(guardrails),
        },
        "latency_ms": latency_ms,
    }
    return body


def validate_alert(alert: Mapping[str, Any]) -> tuple[str, Severity]:
    """Reject an alert before any matcher call. Returns ``(alert_id, severity)``."""
    alert_id = alert.get("alert_id")
    if not isinstance(alert_id, str) or alert_id.strip() == "":
        raise ValueError("alert.alert_id is required")
    severity = alert.get("splunk_severity")
    if not isinstance(severity, str) or not _is_severity(severity):
        raise ValueError(
            "alert.splunk_severity must be informational, low, medium, high, or critical"
        )
    return alert_id, cast(Severity, severity)


def _is_severity(value: str) -> bool:
    return value in SEVERITY_ORDER


def _guardrails(rules: Sequence[RuleResult], fuzzy_missing: bool) -> list[str]:
    guardrails: list[str] = []
    if fuzzy_missing:
        guardrails.append(GUARDRAIL)
    if any(rule.matched and rule.effect.op == "never_auto_close" for rule in rules):
        guardrails.append(NEVER_AUTO_CLOSE_GUARDRAIL)
    return guardrails


def _candidate_labels(
    direction: Direction,
    rules: Sequence[RuleResult],
    fuzzy: FuzzyMatchResult | None,
    certainties: Mapping[str, float],
) -> list[dict[str, Any]]:
    # Unchanged enqueue carries no candidate label (ADR-0005). Escalation and
    # downgrade keep the labels the rules and the matcher actually produced.
    if direction == "unchanged":
        return []
    labels: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for rule in rules:
        if not rule.matched:
            continue
        certainty = certainties.get(rule.rule_id, DEFAULT_RULE_CERTAINTY)
        for name in rule.labels:
            _add_label(labels, seen, name, "rule", certainty)
    if fuzzy is not None:
        for name in fuzzy.suggested_labels:
            _add_label(labels, seen, name, "fuzzy", _units(fuzzy.confidence))
    return labels


def _add_label(
    labels: list[dict[str, Any]],
    seen: set[tuple[str, str]],
    name: str,
    source: LabelSource,
    confidence: float,
) -> None:
    key = (name, source)
    if key in seen:
        return
    seen.add(key)
    labels.append({"name": name, "source": source, "confidence": confidence})


def _rationale(
    direction: Direction,
    disposition: str,
    original: Severity,
    final: Severity,
    confidence: float,
    rules: Sequence[RuleResult],
    fuzzy: FuzzyMatchResult | None,
    guardrails: Sequence[str],
    config: RoutingConfig,
) -> str:
    if direction == "escalated":
        return _escalated_rationale(original, final, rules, fuzzy, config)
    if direction == "downgraded":
        return _downgraded_rationale(
            disposition, original, final, confidence, guardrails, config
        )
    if direction == "unchanged":
        return _unchanged_rationale(disposition, final, guardrails)
    never: Never = direction  # pragma: no cover
    return never  # pragma: no cover


def _escalated_rationale(
    original: Severity,
    final: Severity,
    rules: Sequence[RuleResult],
    fuzzy: FuzzyMatchResult | None,
    config: RoutingConfig,
) -> str:
    bits = _effect_bits(rules)
    fuzzy_bit = _fuzzy_bit(original, final, fuzzy, config)
    if fuzzy_bit:
        bits.append(fuzzy_bit)
    cause = ", ".join(bits)
    return (
        f"Escalated {original}->{final}: {cause}. "
        "Escalations always go to the human queue."
    )


def _downgraded_rationale(
    disposition: str,
    original: Severity,
    final: Severity,
    confidence: float,
    guardrails: Sequence[str],
    config: RoutingConfig,
) -> str:
    shown = _fmt(confidence)
    threshold = _fmt(config.auto_close_min_confidence)
    if disposition == "auto_closed":
        return (
            f"Downgraded {original}->{final} with confidence {shown} >= {threshold}, "
            "no never_auto_close rule matched: auto-close with audit record."
        )
    reasons: list[str] = []
    if GUARDRAIL in guardrails:
        reasons.append("fuzzy matcher timed out")
    if NEVER_AUTO_CLOSE_GUARDRAIL in guardrails:
        reasons.append("never_auto_close matched")
    if AUTO_CLOSE_SAMPLE_GUARDRAIL in guardrails:
        percent = int(round(config.sample_rate * 100))
        reasons.append(f"selected for the {percent}% downgrade-review sample")
    if reasons:
        because = reasons[0] if len(reasons) == 1 else f"{reasons[0]} and {reasons[1]}"
        return (
            f"Downgraded {original}->{final} with confidence {shown}: "
            f"{because}; enqueue for downgrade review."
        )
    return (
        f"Downgraded {original}->{final} with confidence {shown} < {threshold}: "
        "enqueue for downgrade review."
    )


def _unchanged_rationale(disposition: str, final: Severity, guardrails: Sequence[str]) -> str:
    if disposition == "recorded_only":
        text = f"Unchanged at {final}: recorded only."
    else:
        text = (
            f"Unchanged at {final}: pass through to the human queue at standard priority "
            "(no candidate label)."
        )
    if GUARDRAIL in guardrails:
        text += " Fuzzy matcher timed out; deterministic path only."
    return text


def _effect_bits(rules: Sequence[RuleResult]) -> list[str]:
    bits: list[str] = []
    for rule in rules:
        if not rule.matched:
            continue
        bit = _effect_bit(rule.effect)
        if bit is not None:
            bits.append(bit)
    return bits


def _effect_bit(effect: SeverityEffect) -> str | None:
    op = effect.op
    if op == "floor" or op == "ceiling" or op == "set":
        if effect.severity is None:
            return None
        return f"rule {op}={effect.severity}"
    if op == "delta":
        return f"rule delta={effect.delta:+d}"
    if op == "never_auto_close" or op == "none":
        return None
    never: Never = op  # pragma: no cover
    return never  # pragma: no cover


def _fuzzy_bit(
    original: Severity,
    final: Severity,
    fuzzy: FuzzyMatchResult | None,
    config: RoutingConfig,
) -> str:
    if fuzzy is None:
        return ""
    shown = _fmt(fuzzy.confidence)
    minimum = _fmt(config.fuzzy_min_confidence)
    if fuzzy.confidence >= config.fuzzy_min_confidence:
        if _agrees(original, final, fuzzy.suggested_severity):
            return f"fuzzy agrees ({shown} >= {minimum})"
        return f"fuzzy suggests {fuzzy.suggested_severity} ({shown} >= {minimum})"
    return f"fuzzy confidence {shown} < {minimum}"


def _agrees(original: Severity, final: Severity, suggested: Severity) -> bool:
    return rank(suggested) == rank(final) or rank(suggested) > rank(original)


def _rule_payload(rule: RuleResult) -> dict[str, Any]:
    body: dict[str, Any] = {
        "rule_id": rule.rule_id,
        "rule_version": rule.rule_version,
        "matched": rule.matched,
        "effect": _effect_payload(rule.effect),
        "rationale": rule.rationale,
    }
    if rule.labels:
        body["labels"] = list(rule.labels)
    if rule.evidence_refs:
        body["evidence_refs"] = list(rule.evidence_refs)
    return body


def _effect_payload(effect: SeverityEffect) -> dict[str, Any]:
    body: dict[str, Any] = {"op": effect.op}
    if effect.severity is not None:
        body["severity"] = effect.severity
    if effect.op == "delta":
        body["delta"] = effect.delta
    return body


def _fuzzy_payload(fuzzy: FuzzyMatchResult) -> dict[str, Any]:
    body: dict[str, Any] = {
        "matcher_id": fuzzy.matcher_id,
        "model": fuzzy.model,
        "similar_items": [_similar_payload(item) for item in fuzzy.similar_items],
        "suggested_severity": fuzzy.suggested_severity,
        "confidence": fuzzy.confidence,
        "rationale": fuzzy.rationale,
    }
    if fuzzy.suggested_labels:
        body["suggested_labels"] = list(fuzzy.suggested_labels)
    return body


def _similar_payload(item: SimilarItem) -> dict[str, Any]:
    body: dict[str, Any] = {
        "ref_type": item.ref_type,
        "ref_id": item.ref_id,
        "similarity": item.similarity,
    }
    if item.verified_severity is not None:
        body["verified_severity"] = item.verified_severity
    body["verdict"] = item.verdict
    body["summary"] = item.summary
    return body


def _units(value: float) -> float:
    return round(value, 2)


def _fmt(value: float) -> str:
    return f"{round(float(value), 2):.2f}".rstrip("0").rstrip(".")
