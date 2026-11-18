"""Grok Bot API: queue, claim, enrichments, proposals (T16 minimal slice)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import NoResultFound
from starlette.responses import Response
from triage_db.queue import bot_claim
from triage_db.repositories.actions import save_action
from triage_db.repositories.case_query import list_bot_queue
from triage_db.repositories.evidence import append_evidence_item
from triage_db.repositories.next_steps import get_next_steps_pack, replace_next_steps_pack

from app.action_handlers import _now as action_now
from app.audit import AuthDeniedNotice
from app.case_handlers import _load_case, sync_case_pending_actions
from app.database import db_connection
from app.principals import BotPrincipal
from app.problems import problem
from app.request_helpers import actor_from_request


def _principal_bot(request: Request) -> BotPrincipal | None:
    principal = getattr(request.state, "principal", None)
    if isinstance(principal, BotPrincipal):
        return principal
    return None


def _deny_wrong_analyst(request: Request, *, operation_id: str, case_id: str) -> JSONResponse:
    bot = _principal_bot(request)
    if bot is None:
        return problem(status=403, detail="Forbidden.", instance=request.url.path)
    hook = request.app.state.audit
    hook.record_auth_denied(
        AuthDeniedNotice(
            event_type="auth.denied",
            actor=bot,
            operation_id=operation_id,
            instance=request.url.path,
            case_id=case_id,
            action_id=None,
        )
    )
    return problem(
        status=403,
        detail="Case is not assigned to this bot's analyst.",
        instance=request.url.path,
    )


def _case_visible_to_bot(case: dict[str, Any], bot: BotPrincipal) -> bool:
    return case.get("assignee") == bot.on_behalf_of


async def bot_list_queue_handler(request: Request) -> JSONResponse | dict[str, Any]:
    bot = _principal_bot(request)
    if bot is None:
        return problem(status=401, detail="Missing or invalid credentials.", instance=request.url.path)
    limit_raw = request.query_params.get("limit", "5")
    try:
        limit = int(limit_raw)
    except ValueError:
        limit = 5
    limit = min(max(limit, 1), 20)
    with db_connection() as conn:
        items = list_bot_queue(conn, analyst_id=bot.on_behalf_of, bot_id=bot.id, limit=limit)
    return {"items": items, "next_cursor": None}


async def bot_claim_handler(request: Request) -> Response | dict[str, Any]:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return problem(status=422, detail="Invalid JSON body.", instance=str(request.url.path))
    if not isinstance(body, dict) or "queue" not in body:
        return problem(status=422, detail="queue is required.", instance=str(request.url.path))
    queue = str(body["queue"])
    max_items = int(body.get("max_items", 1))
    lease_seconds = int(body.get("lease_seconds", 900))
    actor = actor_from_request(request)
    with db_connection() as conn:
        claimed = bot_claim(
            conn,
            queue=queue,
            claimed_by=actor,
            max_items=max_items,
            lease_seconds=lease_seconds,
        )
    if not claimed:
        return Response(status_code=204)
    return {"items": claimed}


async def bot_add_enrichment_handler(request: Request, case_id: str) -> JSONResponse:
    bot = _principal_bot(request)
    if bot is None:
        return problem(status=401, detail="Missing or invalid credentials.", instance=request.url.path)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return problem(status=422, detail="Invalid JSON body.", instance=str(request.url.path))
    if not isinstance(body, dict):
        return problem(status=422, detail="Request body must be a JSON object.", instance=str(request.url.path))
    for key in ("kind", "title", "source"):
        if key not in body:
            return problem(status=422, detail=f"{key} is required.", instance=str(request.url.path))
    actor = actor_from_request(request)
    with db_connection() as conn:
        try:
            case = _load_case(conn, case_id)
        except LookupError:
            return problem(status=404, detail=f"Case {case_id} was not found.", instance=str(request.url.path))
        if not _case_visible_to_bot(case, bot):
            return _deny_wrong_analyst(request, operation_id="botAddEnrichment", case_id=case_id)
        pack_id = case.get("evidence_pack_id")
        if not pack_id:
            return problem(status=404, detail=f"No evidence pack for case {case_id}.", instance=str(request.url.path))
        item: dict[str, Any] = {
            "evidence_id": f"ev-bot-{uuid.uuid4().hex[:8]}",
            "kind": str(body["kind"]),
            "title": str(body["title"]),
            "source": str(body["source"]),
            "collected_at": _now(),
            "added_by": actor,
        }
        if isinstance(body.get("data"), dict):
            item["data"] = body["data"]
        if body.get("link") is not None:
            item["link"] = str(body["link"])
        note_line = str(body["title"])
        pack = append_evidence_item(
            conn,
            str(pack_id),
            item,
            actor=actor,
            summary_suffix=note_line,
        )
    return JSONResponse(status_code=201, content=pack)


async def bot_propose_handler(request: Request, case_id: str) -> JSONResponse:
    bot = _principal_bot(request)
    if bot is None:
        return problem(status=401, detail="Missing or invalid credentials.", instance=request.url.path)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return problem(status=422, detail="Invalid JSON body.", instance=str(request.url.path))
    if not isinstance(body, dict) or not isinstance(body.get("actions"), list):
        return problem(status=422, detail="actions is required.", instance=str(request.url.path))
    actor = actor_from_request(request)
    with db_connection() as conn:
        try:
            case = _load_case(conn, case_id)
        except LookupError:
            return problem(status=404, detail=f"Case {case_id} was not found.", instance=str(request.url.path))
        if not _case_visible_to_bot(case, bot):
            return _deny_wrong_analyst(request, operation_id="botPropose", case_id=case_id)
        for raw in body["actions"]:
            if not isinstance(raw, dict):
                continue
            for key in ("type", "params", "rationale", "risk"):
                if key not in raw:
                    return problem(status=422, detail=f"{key} is required.", instance=str(request.url.path))
            action: dict[str, Any] = {
                "action_id": str(uuid.uuid4()),
                "case_id": case_id,
                "type": str(raw["type"]),
                "params": raw["params"] if isinstance(raw["params"], dict) else {},
                "rationale": str(raw["rationale"]),
                "risk": str(raw["risk"]),
                "status": "proposed",
                "requires_approval": True,
                "proposed_by": actor,
                "proposed_at": action_now(),
            }
            save_action(conn, action, actor=actor)
        pack_id = case.get("next_steps_pack_id")
        if not pack_id:
            return problem(status=404, detail=f"No next-steps pack for case {case_id}.", instance=str(request.url.path))
        try:
            pack = get_next_steps_pack(conn, str(pack_id))
        except NoResultFound:
            return problem(status=404, detail=f"Next-steps pack for case {case_id} was not found.", instance=str(request.url.path))
        patch: dict[str, Any] = {
            "version": int(pack["version"]) + 1,
            "generated_at": _now(),
            "generated_by": actor,
        }
        drafts = body.get("draft_responses")
        if isinstance(drafts, list):
            patch["draft_responses"] = drafts
        summary = body.get("summary")
        if isinstance(summary, str) and summary.strip():
            evidence_id = case.get("evidence_pack_id")
            if evidence_id:
                try:
                    append_evidence_item(
                        conn,
                        str(evidence_id),
                        {
                            "evidence_id": f"ev-bot-sum-{uuid.uuid4().hex[:8]}",
                            "kind": "llm_reasoning",
                            "title": summary.strip()[:500],
                            "source": "grok-bot",
                            "collected_at": _now(),
                            "added_by": actor,
                        },
                        actor=actor,
                        summary_suffix=summary.strip(),
                    )
                except NoResultFound:
                    pass
        updated = replace_next_steps_pack(conn, {**pack, **patch}, actor=actor)
        sync_case_pending_actions(conn, case_id, actor)
    return JSONResponse(status_code=201, content=updated)


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")