"""Triage Agent internal contract (Python). Owned by the Triage-Agent/ML engineer.

This file is a *contract stub*: Protocols + data shapes + deterministic mocks.
It deliberately contains no production logic except the routing policy table,
which is part of the contract (ADR-0005) and is unit-checked by
scripts/validate_contracts.py.

Wire-level shapes mirror contracts/schemas/triage-decision.schema.json
($defs RuleResult, FuzzyMatchResult). Implementations must return dicts/objects
that serialise to those schemas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Optional, Protocol, Sequence, runtime_checkable

Severity = Literal["informational", "low", "medium", "high", "critical"]
SEVERITY_ORDER: tuple[Severity, ...] = ("informational", "low", "medium", "high", "critical")
Disposition = Literal[
    "enqueue_for_triage", "enqueue_downgrade_review", "auto_closed", "auto_suppressed", "recorded_only"
]


def rank(s: Severity) -> int:
    return SEVERITY_ORDER.index(s)


# --------------------------------------------------------------------------- data


@dataclass(frozen=True)
class SeverityEffect:
    op: Literal["floor", "ceiling", "set", "delta", "never_auto_close", "none"]
    severity: Optional[Severity] = None
    delta: int = 0


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    rule_version: str
    matched: bool
    effect: SeverityEffect
    rationale: str
    labels: Sequence[str] = ()
    evidence_refs: Sequence[str] = ()


@dataclass(frozen=True)
class SimilarItem:
    ref_type: Literal["past_incident", "known_pattern", "benign_baseline"]
    ref_id: str
    similarity: float
    summary: str
    verified_severity: Optional[Severity] = None
    verdict: str = "unknown"


@dataclass(frozen=True)
class FuzzyMatchResult:
    matcher_id: str
    model: str
    similar_items: Sequence[SimilarItem]
    suggested_severity: Severity
    confidence: float
    rationale: str
    suggested_labels: Sequence[str] = ()


@dataclass
class TriageContext:
    """Read-only lookups the agent may use. Injected so tests can stub them."""

    asset_inventory: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)  # host -> {crown_jewel, group}
    identity_directory: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)  # user -> {privileged, dept}
    allow_lists: Mapping[str, Sequence[str]] = field(default_factory=dict)  # name -> values
    now_iso: str = ""


# --------------------------------------------------------------------------- plugin interfaces


@runtime_checkable
class RulePlugin(Protocol):
    """Deterministic rule. Pure function of (alert, context). Must not do network I/O.

    Rules are discovered from `triage_agent.rules` entry points / a rules/ package and
    run in ascending `priority`. A rule that does not apply returns matched=False.
    """

    rule_id: str
    version: str
    priority: int

    def applies_to(self, alert: Mapping[str, Any]) -> bool: ...

    def evaluate(self, alert: Mapping[str, Any], ctx: TriageContext) -> RuleResult: ...


@runtime_checkable
class FuzzyMatcher(Protocol):
    """AI-based similarity: embeddings kNN over past incidents/known patterns, optionally
    followed by an LLM judge. MUST be mockable and MUST honour `timeout_s`; on timeout
    the agent falls back to rules-only and records guardrail `fuzzy_timeout_fallback`."""

    matcher_id: str

    def match(self, alert: Mapping[str, Any], k: int = 5, timeout_s: float = 5.0) -> FuzzyMatchResult: ...


@runtime_checkable
class LLMClient(Protocol):
    """Thin seam over any LLM provider. Structured output only (JSON matching `schema`)."""

    model: str

    def complete_json(self, system: str, user: str, schema: Mapping[str, Any], timeout_s: float = 10.0) -> dict: ...


class RoutingPolicy(Protocol):
    def route(self, original: Severity, final: Severity, confidence: float, *, never_auto_close: bool) -> Disposition: ...


class TriageAgent(Protocol):
    """Top-level contract consumed by the Backend worker.

    Input : Alert (alert.schema.json)
    Output: TriageDecision (triage-decision.schema.json) and, when disposition is
            enqueue_*, an EvidencePack and NextStepsPack (their schemas).
    Must be deterministic given the same alert, context, rules and *mocked* matcher.
    """

    def triage(self, alert: Mapping[str, Any], ctx: TriageContext) -> dict: ...

    def build_evidence_pack(self, alert: Mapping[str, Any], decision: Mapping[str, Any]) -> dict: ...

    def build_next_steps(self, alert: Mapping[str, Any], decision: Mapping[str, Any]) -> dict: ...


# --------------------------------------------------------------------------- policy (contracted)


class DefaultRoutingPolicy:
    """ADR-0005 routing table.

    escalated                                   -> enqueue_for_triage (+ candidate label)
    downgraded, conf >= 0.85, no guard rule     -> auto_closed (audit record, re-openable)
    downgraded otherwise                        -> enqueue_downgrade_review (low priority)
    unchanged, final >= medium                  -> enqueue_for_triage (standard priority)
    unchanged, final <  medium                  -> recorded_only
    """

    AUTO_CLOSE_MIN_CONFIDENCE = 0.85

    def route(self, original: Severity, final: Severity, confidence: float, *, never_auto_close: bool) -> Disposition:
        if rank(final) > rank(original):
            return "enqueue_for_triage"
        if rank(final) < rank(original):
            if confidence >= self.AUTO_CLOSE_MIN_CONFIDENCE and not never_auto_close:
                return "auto_closed"
            return "enqueue_downgrade_review"
        return "enqueue_for_triage" if rank(final) >= rank("medium") else "recorded_only"


def combine_severity(original: Severity, rules: Sequence[RuleResult], fuzzy: Optional[FuzzyMatchResult],
                     fuzzy_min_conf: float = 0.75) -> Severity:
    """Contracted combination order (ADR-0005), shown for reference implementers:
    1. start at the Splunk severity; 2. apply `set`, then `delta` from matched rules;
    3. fuzzy may move the result at most ONE level toward its suggestion if confidence >= fuzzy_min_conf;
    4. clamp by the max matched `floor` and min matched `ceiling` (rules always win over AI)."""
    r = rank(original)
    matched = [x for x in rules if x.matched]
    for x in matched:
        if x.effect.op == "set" and x.effect.severity:
            r = rank(x.effect.severity)
    for x in matched:
        if x.effect.op == "delta":
            r += x.effect.delta
    if fuzzy and fuzzy.confidence >= fuzzy_min_conf:
        target = rank(fuzzy.suggested_severity)
        r += (target > r) - (target < r)
    floors = [rank(x.effect.severity) for x in matched if x.effect.op == "floor" and x.effect.severity]
    ceils = [rank(x.effect.severity) for x in matched if x.effect.op == "ceiling" and x.effect.severity]
    if floors:
        r = max(r, max(floors))
    if ceils:
        r = min(r, min(ceils))
    return SEVERITY_ORDER[max(0, min(r, len(SEVERITY_ORDER) - 1))]


# --------------------------------------------------------------------------- mocks (for tests & demo)


class MockFuzzyMatcher:
    """Deterministic: looks up `fixtures` by search_name; default echoes Splunk severity."""

    matcher_id = "mock-fuzzy"

    def __init__(self, fixtures: Optional[Mapping[str, FuzzyMatchResult]] = None):
        self.fixtures = dict(fixtures or {})

    def match(self, alert: Mapping[str, Any], k: int = 5, timeout_s: float = 5.0) -> FuzzyMatchResult:
        key = alert.get("source", {}).get("search_name", "")
        if key in self.fixtures:
            return self.fixtures[key]
        return FuzzyMatchResult(self.matcher_id, "mock", (), alert.get("splunk_severity", "medium"), 0.5,
                                "No fixture; neutral echo of Splunk severity.")


class MockLLMClient:
    model = "mock-llm"

    def __init__(self, canned: Optional[Mapping[str, dict]] = None):
        self.canned = dict(canned or {})

    def complete_json(self, system: str, user: str, schema: Mapping[str, Any], timeout_s: float = 10.0) -> dict:
        for needle, out in self.canned.items():
            if needle in user:
                return out
        return {}
