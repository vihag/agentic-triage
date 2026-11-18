"""Constructors for contract ``RuleResult`` values."""

from __future__ import annotations

from collections.abc import Sequence

from triage_agent.contract import RuleResult, SeverityEffect


def unmatched(rule_id: str, version: str, rationale: str) -> RuleResult:
    return RuleResult(rule_id, version, False, SeverityEffect("none"), rationale)


def matched(
    rule_id: str,
    version: str,
    effect: SeverityEffect,
    rationale: str,
    *,
    labels: Sequence[str] = (),
    evidence_refs: Sequence[str] = (),
) -> RuleResult:
    return RuleResult(rule_id, version, True, effect, rationale, labels, evidence_refs)
