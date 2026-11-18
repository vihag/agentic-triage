"""Triage one alert into a TriageDecision. CI injects a mock matcher.

Pack builders are T12. This type implements ``TriageAgent.triage`` only.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from triage_agent.contract import (
    DefaultRoutingPolicy,
    FuzzyMatcher,
    RoutingPolicy,
    RulePlugin,
    TriageContext,
)
from triage_agent.engine import RuleEngine
from triage_agent.fuzzy.fallback import match_or_rules_only
from triage_agent.routing import RoutingConfig, build_decision, validate_alert


class DefaultTriageAgent:
    """Rules, then the matcher, then ADR-0005 combine and route.

    ``matcher`` is required. Pass ``MockFuzzyMatcher`` or a timeout stub in CI.
    A live ``PgvectorFuzzyMatcher`` belongs in the worker, with ``MockLLMClient``
    until a nightly drift job opts into a real model.
    """

    def __init__(
        self,
        matcher: FuzzyMatcher,
        *,
        engine: RuleEngine | None = None,
        policy: RoutingPolicy | None = None,
        config: RoutingConfig | None = None,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        new_id: Callable[[], str] | None = None,
        k: int = 5,
        timeout_s: float = 5.0,
    ) -> None:
        self.matcher = matcher
        self.engine = engine if engine is not None else RuleEngine()
        self.policy = policy if policy is not None else DefaultRoutingPolicy()
        self.config = config if config is not None else RoutingConfig()
        self._clock = clock if clock is not None else _utc_now
        self._monotonic = monotonic if monotonic is not None else time.monotonic
        self._new_id = new_id if new_id is not None else _new_id
        self.k = k
        self.timeout_s = timeout_s

    def triage(self, alert: Mapping[str, Any], ctx: TriageContext) -> dict[str, Any]:
        if not isinstance(alert, Mapping):
            raise TypeError("alert must be a mapping")
        if not isinstance(ctx, TriageContext):
            raise TypeError("ctx must be a TriageContext")
        validate_alert(alert)
        started = self._monotonic()
        rules = self.engine.run(alert, ctx)
        outcome = match_or_rules_only(
            self.matcher, alert, k=self.k, timeout_s=self.timeout_s
        )
        elapsed = self._monotonic() - started
        return build_decision(
            alert,
            rules,
            outcome,
            policy=self.policy,
            config=self.config,
            decision_id=self._new_id(),
            decided_at=_iso(self._clock()),
            latency_ms=max(0, int(elapsed * 1000)),
            certainties=plugin_certainties(self.engine.rules),
        )


def plugin_certainties(rules: Sequence[RulePlugin]) -> dict[str, float]:
    """Read ``certainty`` from each plugin. Rules that omit it use the default."""
    found: dict[str, float] = {}
    for rule in rules:
        value = getattr(rule, "certainty", None)
        if isinstance(value, float):
            found[rule.rule_id] = value
    return found


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        aware = moment.replace(tzinfo=UTC)
    else:
        aware = moment.astimezone(UTC)
    return aware.strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id() -> str:
    return str(uuid4())
