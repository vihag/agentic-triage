"""Build a Case document from Alert + TriageDecision."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from triage_agent.contract import SEVERITY_ORDER

_QUEUED = frozenset({"enqueue_for_triage", "enqueue_downgrade_review"})


def _rank(severity: str) -> int:
    return SEVERITY_ORDER.index(severity)


def _ts() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_priority(final_severity: str, confidence: float) -> int:
    return min(100, max(0, _rank(final_severity) * 20 + int(confidence * 100)))


def route_case(decision: Mapping[str, Any]) -> tuple[str, str, int, dict[str, Any] | None]:
    """Return status, queue, priority basis severity, optional resolution."""
    disposition = str(decision["disposition"])
    final = str(decision["final_severity"])
    confidence = float(decision.get("confidence", 0.5))
    if disposition == "auto_closed":
        return (
            "auto_closed",
            "soc-standard",
            compute_priority(final, confidence),
            {
                "outcome": "auto_closed_downgrade",
                "note": decision.get("policy", {}).get("rationale", "Auto-closed by policy."),
            },
        )
    if disposition == "recorded_only":
        return (
            "auto_closed",
            "soc-standard",
            compute_priority(final, confidence),
            {"outcome": "recorded", "note": "Recorded only; no queue."},
        )
    if disposition == "enqueue_downgrade_review":
        return "queued", "soc-downgrade-review", min(30, compute_priority(final, confidence)), None
    queue = "soc-high" if decision.get("direction") == "escalated" else "soc-standard"
    return "queued", queue, compute_priority(final, confidence), None


def build_case(
    *,
    alert: Mapping[str, Any],
    decision: Mapping[str, Any],
    assignee: str | None,
    evidence_pack_id: str | None,
    next_steps_pack_id: str | None,
    pending_action_count: int,
    case_id: str | None = None,
) -> dict[str, Any]:
    now = _ts()
    status, queue, priority, resolution = route_case(decision)
    case_id = case_id or str(uuid4())
    body: dict[str, Any] = {
        "case_id": case_id,
        "alert_ids": [alert["alert_id"]],
        "decision_id": decision["decision_id"],
        "title": alert.get("title", "Alert"),
        "severity": decision["final_severity"],
        "original_severity": decision["original_severity"],
        "direction": decision["direction"],
        "status": status,
        "queue": queue,
        "priority": priority,
        "assignee": assignee if status == "queued" else None,
        "claimed_by": None,
        "lease_expires_at": None,
        "candidate_labels": decision.get("candidate_labels") or [],
        "pending_action_count": pending_action_count,
        "resolution": resolution,
        "created_at": now,
        "updated_at": now,
        "version": 1,
    }
    if evidence_pack_id is not None:
        body["evidence_pack_id"] = evidence_pack_id
    if next_steps_pack_id is not None:
        body["next_steps_pack_id"] = next_steps_pack_id
    return body