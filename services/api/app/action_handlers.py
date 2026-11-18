"""Proposed actions: list, propose, approve, reject."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import NoResultFound
from triage_db.repositories.action_query import list_actions_for_case, replace_action
from triage_db.repositories.actions import get_action, save_action

from app.case_handlers import _load_case, sync_case_pending_actions
from app.database import db_connection
from app.executor import execute_approved_action
from app.problems import conflict, not_found, problem
from app.request_helpers import actor_from_request


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


async def list_actions_handler(
    request: Request, case_id: str
) -> JSONResponse | list[dict[str, object]]:
    with db_connection() as conn:
        try:
            _load_case(conn, case_id)
        except LookupError:
            return not_found(request, f"Case {case_id} was not found.")
        return list_actions_for_case(conn, case_id)


async def propose_action_handler(request: Request, case_id: str) -> JSONResponse:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return problem(status=422, detail="Invalid JSON body.", instance=str(request.url.path))
    if not isinstance(body, dict):
        return problem(status=422, detail="Request body must be a JSON object.", instance=str(request.url.path))
    required = ("type", "params", "rationale", "risk")
    for key in required:
        if key not in body:
            return problem(status=422, detail=f"{key} is required.", instance=str(request.url.path))
    actor = actor_from_request(request)
    action: dict[str, Any] = {
        "action_id": str(uuid.uuid4()),
        "case_id": case_id,
        "type": str(body["type"]),
        "params": body["params"] if isinstance(body["params"], dict) else {},
        "rationale": str(body["rationale"]),
        "risk": str(body["risk"]),
        "status": "proposed",
        "requires_approval": True,
        "proposed_by": actor,
        "proposed_at": _now(),
    }
    with db_connection() as conn:
        try:
            _load_case(conn, case_id)
        except LookupError:
            return not_found(request, f"Case {case_id} was not found.")
        save_action(conn, action, actor=actor)
        sync_case_pending_actions(conn, case_id, actor)
    return JSONResponse(status_code=201, content=action)


async def approve_action_handler(
    request: Request, case_id: str, action_id: str
) -> JSONResponse:
    note: str | None = None
    if request.headers.get("content-length", "0") not in ("0", ""):
        try:
            body = await request.json()
            if isinstance(body, dict) and body.get("note") is not None:
                note = str(body["note"])
        except json.JSONDecodeError:
            return problem(status=422, detail="Invalid JSON body.", instance=str(request.url.path))
    actor = actor_from_request(request)
    with db_connection() as conn:
        try:
            action = get_action(conn, action_id)
        except NoResultFound:
            return not_found(request, f"Action {action_id} was not found.")
        if action["case_id"] != case_id:
            return not_found(request, f"Action {action_id} was not found.")
        if action["status"] != "proposed":
            return conflict(request, f"Action is {action['status']}, not proposed.")
        approved = {
            **action,
            "status": "approved",
            "decided_by": actor,
            "decided_at": _now(),
        }
        if note is not None:
            approved["decision_note"] = note
        replace_action(conn, approved, actor=actor)
        executed = execute_approved_action(conn, approved)
        sync_case_pending_actions(conn, case_id, actor)
    return JSONResponse(content=executed)


async def reject_action_handler(
    request: Request, case_id: str, action_id: str
) -> JSONResponse:
    note: str | None = None
    if request.headers.get("content-length", "0") not in ("0", ""):
        try:
            body = await request.json()
            if isinstance(body, dict) and body.get("note") is not None:
                note = str(body["note"])
        except json.JSONDecodeError:
            return problem(status=422, detail="Invalid JSON body.", instance=str(request.url.path))
    actor = actor_from_request(request)
    with db_connection() as conn:
        try:
            action = get_action(conn, action_id)
        except NoResultFound:
            return not_found(request, f"Action {action_id} was not found.")
        if action["case_id"] != case_id:
            return not_found(request, f"Action {action_id} was not found.")
        if action["status"] != "proposed":
            return conflict(request, f"Action is {action['status']}, not proposed.")
        rejected = {
            **action,
            "status": "rejected",
            "decided_by": actor,
            "decided_at": _now(),
        }
        if note is not None:
            rejected["decision_note"] = note
        replace_action(conn, rejected, actor=actor)
        sync_case_pending_actions(conn, case_id, actor)
    return JSONResponse(content=rejected)