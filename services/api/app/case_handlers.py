"""Case list/get, queue claim/release, assign, and transitions."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import NoResultFound
from starlette.responses import Response
from triage_db.queue import claim_next, release_case
from triage_db.repositories.action_query import count_proposed
from triage_db.repositories.case_query import (
    IllegalTransitionError,
    VersionMismatchError,
    bump_version,
    list_cases,
    replace_case,
)
from triage_db.repositories.cases import get_case
from triage_db.repositories.evidence import get_evidence_pack
from triage_db.repositories.next_steps import get_next_steps_pack

from app.case_machine import assert_transition
from app.database import db_connection
from app.problems import conflict, not_found, precondition_failed, problem
from app.request_helpers import actor_from_request, etag_for_version, parse_if_match


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _case_response(case: dict[str, Any]) -> JSONResponse:
    version = int(case["version"])
    return JSONResponse(content=case, headers={"ETag": etag_for_version(version)})


def _load_case(conn: Any, case_id: str) -> dict[str, Any]:
    try:
        return get_case(conn, case_id)
    except NoResultFound as exc:
        raise LookupError(case_id) from exc


def _not_found_case(request: Request, case_id: str) -> JSONResponse:
    return not_found(request, f"Case {case_id} was not found.")


def _version_error(request: Request, exc: VersionMismatchError) -> JSONResponse:
    return precondition_failed(
        request,
        detail=f"Expected version {exc.expected}, found {exc.actual}.",
    )


async def list_cases_handler(request: Request) -> dict[str, Any]:
    queue = request.query_params.get("queue")
    assignee = request.query_params.get("assignee")
    limit_raw = request.query_params.get("limit", "50")
    try:
        limit = int(limit_raw)
    except ValueError:
        limit = 50
    statuses = request.query_params.getlist("status")
    status = statuses if statuses else None
    with db_connection() as conn:
        items = list_cases(
            conn,
            queue=queue,
            status=status,
            assignee=assignee,
            limit=limit,
        )
    return {"items": items, "next_cursor": None}


async def get_case_handler(request: Request, case_id: str) -> JSONResponse:
    with db_connection() as conn:
        try:
            case = _load_case(conn, case_id)
        except LookupError:
            return _not_found_case(request, case_id)
    return _case_response(case)


async def get_evidence_pack_handler(request: Request, case_id: str) -> JSONResponse | dict[str, Any]:
    with db_connection() as conn:
        try:
            case = _load_case(conn, case_id)
        except LookupError:
            return _not_found_case(request, case_id)
        pack_id = case.get("evidence_pack_id")
        if not pack_id:
            return not_found(request, f"No evidence pack for case {case_id}.")
        try:
            pack = get_evidence_pack(conn, str(pack_id))
        except NoResultFound:
            return not_found(request, f"Evidence pack for case {case_id} was not found.")
    return pack


async def get_next_steps_pack_handler(
    request: Request, case_id: str
) -> JSONResponse | dict[str, Any]:
    with db_connection() as conn:
        try:
            case = _load_case(conn, case_id)
        except LookupError:
            return _not_found_case(request, case_id)
        pack_id = case.get("next_steps_pack_id")
        if not pack_id:
            return not_found(request, f"No next-steps pack for case {case_id}.")
        try:
            pack = get_next_steps_pack(conn, str(pack_id))
        except NoResultFound:
            return not_found(request, f"Next-steps pack for case {case_id} was not found.")
    return pack


async def claim_next_handler(request: Request) -> Response | dict[str, Any]:
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
        claimed = claim_next(
            conn,
            queue=queue,
            claimed_by=actor,
            max_items=max_items,
            lease_seconds=lease_seconds,
        )
    if not claimed:
        return Response(status_code=204)
    return {"items": claimed}


async def release_case_handler(request: Request, case_id: str) -> JSONResponse:
    expected = parse_if_match(request)
    actor = actor_from_request(request)
    with db_connection() as conn:
        if expected is not None:
            try:
                current = _load_case(conn, case_id)
            except LookupError:
                return _not_found_case(request, case_id)
            if int(current["version"]) != expected:
                return _version_error(request, VersionMismatchError(expected, int(current["version"])))
        try:
            released = release_case(conn, case_id=case_id, released_by=actor)
        except LookupError:
            return conflict(request, "Case is not claimed by you.")
    return _case_response(released)


async def assign_case_handler(request: Request, case_id: str) -> JSONResponse:
    expected = parse_if_match(request)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return problem(status=422, detail="Invalid JSON body.", instance=str(request.url.path))
    if not isinstance(body, dict) or "assignee" not in body:
        return problem(status=422, detail="assignee is required.", instance=str(request.url.path))
    assignee = str(body["assignee"])
    actor = actor_from_request(request)
    with db_connection() as conn:
        try:
            case = _load_case(conn, case_id)
        except LookupError:
            return _not_found_case(request, case_id)
        try:
            updated = replace_case(
                conn,
                bump_version(case, assignee=assignee, updated_at=_now()),
                expected_version=expected,
                actor=actor,
                audit_type="case.assigned",
            )
        except VersionMismatchError as exc:
            return _version_error(request, exc)
    return _case_response(updated)


async def transition_case_handler(request: Request, case_id: str) -> JSONResponse:
    expected = parse_if_match(request)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return problem(status=422, detail="Invalid JSON body.", instance=str(request.url.path))
    if not isinstance(body, dict) or "to_status" not in body:
        return problem(status=422, detail="to_status is required.", instance=str(request.url.path))
    to_status = str(body["to_status"])
    actor = actor_from_request(request)
    with db_connection() as conn:
        try:
            case = _load_case(conn, case_id)
        except LookupError:
            return _not_found_case(request, case_id)
        try:
            assert_transition(case["status"], to_status)
        except IllegalTransitionError as exc:
            return conflict(
                request,
                f"Cannot transition from {exc.from_status} to {exc.to_status}.",
            )
        patch: dict[str, Any] = {"status": to_status, "updated_at": _now()}
        if "reason" in body and body["reason"] is not None:
            resolution = dict(case.get("resolution") or {})
            resolution["reason"] = str(body["reason"])
            if "resolution_code" in body and body["resolution_code"] is not None:
                resolution["code"] = str(body["resolution_code"])
            patch["resolution"] = resolution
        try:
            updated = replace_case(
                conn,
                bump_version(case, **patch),
                expected_version=expected,
                actor=actor,
                audit_type="case.status_changed",
            )
        except VersionMismatchError as exc:
            return _version_error(request, exc)
    return _case_response(updated)


def sync_case_pending_actions(conn: Any, case_id: str, actor: dict[str, Any]) -> dict[str, Any]:
    case = _load_case(conn, case_id)
    pending = count_proposed(conn, case_id)
    patch: dict[str, Any] = {"pending_action_count": pending}
    if pending > 0 and case["status"] in ("in_progress", "claimed"):
        patch["status"] = "awaiting_approval"
    elif pending == 0 and case["status"] == "awaiting_approval":
        patch["status"] = "in_progress"
    return replace_case(
        conn,
        bump_version(case, **patch),
        expected_version=None,
        actor=actor,
        audit_type="case.status_changed",
    )