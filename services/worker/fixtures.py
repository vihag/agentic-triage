"""Load MockFuzzyMatcher fixtures from contract examples."""

from __future__ import annotations

import json
from pathlib import Path

from contracts.agent.interfaces import FuzzyMatchResult, MockFuzzyMatcher, SimilarItem

_REPO = Path(__file__).resolve().parents[2]
_EXAMPLES = _REPO / "contracts" / "examples"


def _fuzzy_from(payload: dict) -> FuzzyMatchResult:
    fuzzy = payload["fuzzy_result"]
    items = tuple(
        SimilarItem(
            item["ref_type"],
            item["ref_id"],
            item["similarity"],
            item["summary"],
            item.get("verified_severity"),
            item.get("verdict", "unknown"),
        )
        for item in fuzzy["similar_items"]
    )
    return FuzzyMatchResult(
        fuzzy["matcher_id"],
        fuzzy["model"],
        items,
        fuzzy["suggested_severity"],
        fuzzy["confidence"],
        fuzzy["rationale"],
        tuple(fuzzy.get("suggested_labels") or ()),
    )


def build_mock_matcher() -> MockFuzzyMatcher:
    fixtures: dict[str, FuzzyMatchResult] = {}
    for name in ("triage-decision.escalate.json", "triage-decision.downgrade.json"):
        payload = json.loads((_EXAMPLES / name).read_text())
        search = None
        if name.endswith("escalate.json"):
            search = "Excessive Failed Logins Followed By Success"
        else:
            search = "Malware Signature Detected On Endpoint"
        fixtures[search] = _fuzzy_from(payload)
    return MockFuzzyMatcher(fixtures)