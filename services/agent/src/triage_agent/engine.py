"""Run discovered rules in ascending priority and keep every result."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from triage_agent.contract import RulePlugin, RuleResult, TriageContext
from triage_agent.loader import discover_rules, materialise
from triage_agent.results import unmatched


class RuleEngine:
    """Evaluate every plugin. A rule that does not apply is still recorded.

    ``rules=None`` discovers the starter package. Pass a sequence to test a
    fixed set without scanning entry points.
    """

    def __init__(self, rules: Sequence[RulePlugin] | None = None) -> None:
        if rules is None:
            chosen = discover_rules()
        else:
            chosen = [materialise(rule, source="RuleEngine") for rule in rules]
            self._ensure_unique(chosen)
        self.rules: tuple[RulePlugin, ...] = tuple(
            sorted(chosen, key=lambda rule: (rule.priority, rule.rule_id))
        )

    def run(self, alert: Mapping[str, Any], ctx: TriageContext | None = None) -> list[RuleResult]:
        if not isinstance(alert, Mapping):
            raise TypeError("alert must be a mapping")
        if ctx is None:
            context = TriageContext()
        elif not isinstance(ctx, TriageContext):
            raise TypeError("ctx must be a TriageContext")
        else:
            context = ctx
        return [self._run_one(rule, alert, context) for rule in self.rules]

    def _run_one(
        self, rule: RulePlugin, alert: Mapping[str, Any], ctx: TriageContext
    ) -> RuleResult:
        if not rule.applies_to(alert):
            return unmatched(
                rule.rule_id,
                rule.version,
                f"{rule.rule_id} does not apply to this alert.",
            )
        result = rule.evaluate(alert, ctx)
        if not isinstance(result, RuleResult):
            raise TypeError(
                f"{rule.rule_id} evaluate() must return RuleResult, got {type(result).__name__}"
            )
        if result.rule_id != rule.rule_id or result.rule_version != rule.version:
            return RuleResult(
                rule.rule_id,
                rule.version,
                result.matched,
                result.effect,
                result.rationale,
                result.labels,
                result.evidence_refs,
            )
        return result

    @staticmethod
    def _ensure_unique(rules: Sequence[RulePlugin]) -> None:
        seen: set[str] = set()
        for rule in rules:
            if rule.rule_id in seen:
                raise ValueError(f"duplicate rule_id {rule.rule_id}")
            seen.add(rule.rule_id)
