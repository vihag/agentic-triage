"""LLM judge. Structured JSON only, checked against FuzzyMatchResult."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from triage_agent.contract import LLMClient, SimilarItem
from triage_agent.fuzzy.errors import FuzzyTimeout
from triage_agent.fuzzy.schema import fuzzy_match_schema, validate_fuzzy_match

_SYSTEM = (
    "You are a SOC severity judge. Return one JSON object matching the schema. "
    "Use only the neighbours provided. Do not invent incidents. "
    "suggested_severity is one of informational, low, medium, high, critical. "
    "confidence is a number from 0 to 1."
)


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def alert_text(alert: Mapping[str, Any]) -> str:
    source = _mapping(alert.get("source"))
    result = _mapping(_mapping(alert.get("raw")).get("result"))
    entities = _mapping(alert.get("entities"))
    parts: list[object] = [
        alert.get("title"),
        alert.get("description"),
        source.get("search_name"),
        result.get("signature"),
        result.get("user"),
    ]
    for key in ("users", "hosts", "src_ips", "dest_ips", "file_hashes"):
        values = entities.get(key)
        if isinstance(values, list):
            parts.extend(values)
    return " ".join(str(part) for part in parts if isinstance(part, str) and part.strip())


def _item_payload(item: SimilarItem) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ref_type": item.ref_type,
        "ref_id": item.ref_id,
        "similarity": item.similarity,
        "summary": item.summary,
        "verdict": item.verdict,
    }
    if item.verified_severity is not None:
        payload["verified_severity"] = item.verified_severity
    return payload


def _user_prompt(alert: Mapping[str, Any], neighbours: Sequence[SimilarItem]) -> str:
    shown = [_item_payload(item) for item in neighbours]
    return (
        f"Alert:\n{alert_text(alert)}\n\n"
        f"Neighbours:\n{shown}\n\n"
        "Judge the alert severity from these neighbours only."
    )


def judge(
    llm: LLMClient,
    alert: Mapping[str, Any],
    neighbours: Sequence[SimilarItem],
    *,
    matcher_id: str,
    model: str,
    timeout_s: float,
) -> dict[str, Any]:
    """Ask the LLM for a judgment and return a validated FuzzyMatchResult dict.

    Neighbours come from kNN. The model does not get to replace them.
    """
    if timeout_s <= 0:
        raise FuzzyTimeout("llm judge timed out")
    try:
        raw = llm.complete_json(
            _SYSTEM,
            _user_prompt(alert, neighbours),
            fuzzy_match_schema(),
            timeout_s,
        )
    except TimeoutError as exc:
        raise FuzzyTimeout("llm judge timed out") from exc
    if not isinstance(raw, dict):
        raise ValueError("llm judge must return a JSON object")
    payload: dict[str, Any] = {
        "matcher_id": matcher_id,
        "model": model,
        "similar_items": [_item_payload(item) for item in neighbours],
        "suggested_severity": raw.get("suggested_severity"),
        "confidence": raw.get("confidence"),
        "rationale": raw.get("rationale"),
    }
    labels = raw.get("suggested_labels")
    if labels is not None:
        payload["suggested_labels"] = labels
    validate_fuzzy_match(payload)
    return payload
