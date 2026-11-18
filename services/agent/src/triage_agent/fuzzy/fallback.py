"""Rules-only path when the matcher does not finish in time."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from triage_agent.contract import FuzzyMatchResult
from triage_agent.fuzzy.errors import FuzzyTimeout

GUARDRAIL = FuzzyTimeout.guardrail


@dataclass(frozen=True)
class FuzzyOutcome:
    """``result`` is None when the agent must stay on deterministic rules."""

    result: FuzzyMatchResult | None
    guardrails: tuple[str, ...]


class _Matcher(Protocol):
    def match(
        self, alert: Mapping[str, Any], k: int = 5, timeout_s: float = 5.0
    ) -> FuzzyMatchResult: ...


def match_or_rules_only(
    matcher: _Matcher,
    alert: Mapping[str, Any],
    *,
    k: int = 5,
    timeout_s: float = 5.0,
) -> FuzzyOutcome:
    """Return the fuzzy result, or rules-only with ``fuzzy_timeout_fallback``."""
    try:
        return FuzzyOutcome(matcher.match(alert, k=k, timeout_s=timeout_s), ())
    except FuzzyTimeout:
        return FuzzyOutcome(None, (GUARDRAIL,))
