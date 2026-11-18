"""Template evidence and next-steps packs for enqueued cases (T12)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from triage_agent.version import agent_version

_AGENT = {"type": "triage_agent", "id": agent_version()}


def _ts(moment: datetime | None = None) -> str:
    when = moment or datetime.now(UTC)
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_evidence_pack(
    *,
    case_id: str,
    alert: Mapping[str, Any],
    decision: Mapping[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    alert_id = str(alert["alert_id"])
    sid = alert.get("source", {}).get("sid", alert_id)
    when = generated_at or _ts()
    summary = decision.get("policy", {}).get("rationale") or alert.get("title", "Triage evidence")
    items: list[dict[str, Any]] = [
        {
            "evidence_id": f"ev-raw-{alert_id[:8]}",
            "kind": "raw_event",
            "title": "Triggering Splunk result",
            "source": f"splunk:sid={sid}",
            "collected_at": when,
            "added_by": _AGENT,
            "data": (
                alert.get("raw", {}).get("result")
                if isinstance(alert.get("raw"), Mapping)
                else None
            ),
        }
    ]
    for row in decision.get("rule_results") or []:
        if not row.get("matched"):
            continue
        items.append(
            {
                "evidence_id": f"ev-rule-{row['rule_id']}",
                "kind": "rule_match",
                "title": row["rule_id"],
                "source": "rule-engine",
                "collected_at": when,
                "added_by": _AGENT,
            }
        )
    fuzzy = decision.get("fuzzy_result")
    if isinstance(fuzzy, Mapping) and fuzzy.get("similar_items"):
        top = fuzzy["similar_items"][0]
        items.append(
            {
                "evidence_id": f"ev-sim-{top.get('ref_id', 'match')}",
                "kind": "similar_incident",
                "title": f"{top.get('ref_id')} (similarity {top.get('similarity')})",
                "source": "fuzzy-matcher",
                "collected_at": when,
                "added_by": _AGENT,
            }
        )
    return {
        "evidence_pack_id": str(uuid4()),
        "case_id": case_id,
        "alert_id": alert_id,
        "version": 1,
        "generated_at": when,
        "generated_by": _AGENT,
        "summary": summary,
        "entities": alert.get("entities") or {},
        "items": items,
        "timeline": [],
    }


def build_next_steps_pack(
    *,
    case_id: str,
    alert: Mapping[str, Any],
    decision: Mapping[str, Any],
    generated_at: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    when = generated_at or _ts()
    search_name = alert.get("source", {}).get("search_name", "")
    playbook = "pb-credential-stuffing-v1"
    if "Malware" in search_name:
        playbook = "pb-malware-on-endpoint-v1"
    elif decision.get("direction") == "downgraded":
        playbook = "pb-downgrade-review-v1"
    action_id = str(uuid4())
    user = None
    entities = alert.get("entities") if isinstance(alert.get("entities"), Mapping) else {}
    users = entities.get("users") if isinstance(entities, Mapping) else None
    if isinstance(users, list) and users:
        user = str(users[0])
    proposed_action = {
        "action_id": action_id,
        "case_id": case_id,
        "type": "disable_user" if user else "close_case",
        "params": {"user": user, "revoke_sessions": True} if user else {},
        "rationale": decision.get("policy", {}).get("rationale", "Proposed by triage agent."),
        "risk": "medium",
        "status": "proposed",
        "requires_approval": True,
        "proposed_by": _AGENT,
        "proposed_at": when,
    }
    steps = [
        {
            "step_id": "s1",
            "order": 1,
            "phase": "investigate",
            "title": "Review evidence and confirm severity",
            "description": alert.get("title", search_name),
        },
        {
            "step_id": "s2",
            "order": 2,
            "phase": "contain",
            "title": "Execute proposed containment",
            "description": "Approve or reject the proposed action once investigation is complete.",
            "proposed_action": proposed_action,
        },
    ]
    pack = {
        "next_steps_pack_id": str(uuid4()),
        "case_id": case_id,
        "version": 1,
        "generated_at": when,
        "generated_by": _AGENT,
        "playbook_id": playbook,
        "steps": steps,
        "draft_responses": [],
    }
    return pack, [proposed_action]