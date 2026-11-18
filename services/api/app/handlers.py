"""Implemented OpenAPI operations (ingest + readbacks for the worker slice)."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import NoResultFound
from triage_db.repositories.alerts import find_alert_by_sid, get_alert, save_alert
from triage_db.repositories.decisions import get_decision_for_alert

from app.database import db_connection
from app.problems import problem
from app.splunk_normalize import normalize_splunk_webhook


async def ingest_splunk_alert(
    request: Request,
    instance: str,
    body: dict[str, Any],
    *,
    query_severity: int | None,
) -> JSONResponse | dict[str, Any]:
    principal = getattr(request.state, "principal", None)
    actor = {"type": "splunk", "id": instance}
    if principal is not None and hasattr(principal, "id"):
        actor["id"] = str(principal.id)
    sid = str(body.get("sid", ""))
    if not sid:
        return problem(status=422, detail="sid is required", instance=str(request.url.path))
    try:
        with db_connection() as conn:
            existing = find_alert_by_sid(conn, sid)
            if existing is not None:
                return JSONResponse(
                    status_code=200,
                    content={
                        "alert_id": existing["alert_id"],
                        "status": "duplicate",
                        "case_id": None,
                    },
                )
            alert = normalize_splunk_webhook(
                body, instance=instance, query_severity=query_severity
            )
            save_alert(conn, alert, actor=actor)
    except ValueError as exc:
        return problem(status=422, detail=str(exc), instance=str(request.url.path))
    except RuntimeError as exc:
        return problem(status=500, detail=str(exc), instance=str(request.url.path))
    return JSONResponse(
        status_code=202,
        content={"alert_id": alert["alert_id"], "status": "accepted", "case_id": None},
    )


async def get_alert_handler(request: Request, alert_id: str) -> JSONResponse | dict[str, Any]:
    try:
        with db_connection() as conn:
            document = get_alert(conn, alert_id)
    except (LookupError, NoResultFound):
        return problem(status=404, detail="Alert not found.", instance=str(request.url.path))
    except RuntimeError as exc:
        return problem(status=500, detail=str(exc), instance=str(request.url.path))
    return document


async def get_triage_decision_handler(
    request: Request, alert_id: str
) -> JSONResponse | dict[str, Any]:
    try:
        with db_connection() as conn:
            document = get_decision_for_alert(conn, alert_id)
    except RuntimeError as exc:
        return problem(status=500, detail=str(exc), instance=str(request.url.path))
    if document is None:
        return problem(status=404, detail="Triage decision not found.", instance=str(request.url.path))
    return document