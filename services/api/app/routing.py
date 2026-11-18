"""Register one route per OpenAPI operation.

healthz is implemented. approve and reject enforce the analyst-only guard.
Every other operation returns 501 after its auth scheme succeeds, including
botGetCaseBundle and listBotRuns. The bot queue slice (list/claim/enrich/propose)
is implemented in T16.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.action_handlers import (
    approve_action_handler,
    list_actions_handler,
    propose_action_handler,
    reject_action_handler,
)
from app.auth import enforce
from app.bot_handlers import (
    bot_add_enrichment_handler,
    bot_claim_handler,
    bot_list_queue_handler,
    bot_propose_handler,
)
from app.case_handlers import (
    assign_case_handler,
    claim_next_handler,
    get_case_handler,
    get_evidence_pack_handler,
    get_next_steps_pack_handler,
    list_cases_handler,
    release_case_handler,
    transition_case_handler,
)
from app.handlers import get_alert_handler, get_triage_decision_handler, ingest_splunk_alert
from app.problems import not_implemented, problem
from app.spec import Operation

_PARAM = re.compile(r"\{([^{}]+)\}")


async def dispatch(
    request: Request, operation: Operation
) -> JSONResponse | Response | dict[str, object] | list[dict[str, object]]:
    blocked = enforce(request, operation)
    if blocked is not None:
        return blocked
    match operation.operation_id:
        case "healthz":
            return {"status": "ok"}
        case "ingestSplunkAlert":
            try:
                body = await request.json()
            except json.JSONDecodeError:
                return problem(
                    status=422,
                    detail="Invalid JSON body.",
                    instance=str(request.url.path),
                )
            if not isinstance(body, dict):
                return problem(
                    status=422,
                    detail="Request body must be a JSON object.",
                    instance=str(request.url.path),
                )
            severity_raw = request.query_params.get("severity")
            query_severity: int | None = None
            if severity_raw is not None:
                try:
                    query_severity = int(severity_raw)
                except ValueError:
                    return not_implemented(request, operation.operation_id)
            instance = _path_param(request, "instance") or "splunk"
            return await ingest_splunk_alert(
                request, instance, body, query_severity=query_severity
            )
        case "getAlert":
            alert_id = _path_param(request, "alert_id")
            if alert_id is None:
                return not_implemented(request, operation.operation_id)
            return await get_alert_handler(request, alert_id)
        case "getTriageDecision":
            alert_id = _path_param(request, "alert_id")
            if alert_id is None:
                return not_implemented(request, operation.operation_id)
            return await get_triage_decision_handler(request, alert_id)
        case "listCases":
            return await list_cases_handler(request)
        case "getCase":
            case_id = _path_param(request, "case_id")
            if case_id is None:
                return not_implemented(request, operation.operation_id)
            return await get_case_handler(request, case_id)
        case "getEvidencePack":
            case_id = _path_param(request, "case_id")
            if case_id is None:
                return not_implemented(request, operation.operation_id)
            return await get_evidence_pack_handler(request, case_id)
        case "getNextStepsPack":
            case_id = _path_param(request, "case_id")
            if case_id is None:
                return not_implemented(request, operation.operation_id)
            return await get_next_steps_pack_handler(request, case_id)
        case "claimNext":
            return await claim_next_handler(request)
        case "releaseCase":
            case_id = _path_param(request, "case_id")
            if case_id is None:
                return not_implemented(request, operation.operation_id)
            return await release_case_handler(request, case_id)
        case "assignCase":
            case_id = _path_param(request, "case_id")
            if case_id is None:
                return not_implemented(request, operation.operation_id)
            return await assign_case_handler(request, case_id)
        case "transitionCase":
            case_id = _path_param(request, "case_id")
            if case_id is None:
                return not_implemented(request, operation.operation_id)
            return await transition_case_handler(request, case_id)
        case "listActions":
            case_id = _path_param(request, "case_id")
            if case_id is None:
                return not_implemented(request, operation.operation_id)
            return await list_actions_handler(request, case_id)
        case "proposeAction":
            case_id = _path_param(request, "case_id")
            if case_id is None:
                return not_implemented(request, operation.operation_id)
            return await propose_action_handler(request, case_id)
        case "approveAction":
            case_id = _path_param(request, "case_id")
            action_id = _path_param(request, "action_id")
            if case_id is None or action_id is None:
                return not_implemented(request, operation.operation_id)
            return await approve_action_handler(request, case_id, action_id)
        case "rejectAction":
            case_id = _path_param(request, "case_id")
            action_id = _path_param(request, "action_id")
            if case_id is None or action_id is None:
                return not_implemented(request, operation.operation_id)
            return await reject_action_handler(request, case_id, action_id)
        case "botListQueue":
            return await bot_list_queue_handler(request)
        case "botClaim":
            return await bot_claim_handler(request)
        case "botAddEnrichment":
            case_id = _path_param(request, "case_id")
            if case_id is None:
                return not_implemented(request, operation.operation_id)
            return await bot_add_enrichment_handler(request, case_id)
        case "botPropose":
            case_id = _path_param(request, "case_id")
            if case_id is None:
                return not_implemented(request, operation.operation_id)
            return await bot_propose_handler(request, case_id)
        case _:
            return not_implemented(request, operation.operation_id)


def _path_param(request: Request, name: str) -> str | None:
    value = request.path_params.get(name)
    if value is None:
        return None
    return str(value)


def register_routes(app: FastAPI, operations: list[Operation]) -> None:
    for operation in operations:
        app.add_api_route(
            operation.path,
            _endpoint(operation),
            methods=[operation.method],
            operation_id=operation.operation_id,
            name=operation.operation_id,
            tags=list(operation.tags),
            response_model=None,
            include_in_schema=False,
        )


def _endpoint(
    operation: Operation,
) -> Callable[..., Awaitable[JSONResponse | Response | dict[str, object] | list[dict[str, object]]]]:
    names = _path_params(operation.path)
    arguments = ", ".join(["request: Request", *(f"{name}: str" for name in names)])
    source = f"async def endpoint({arguments}):\n    return await dispatch(request, OPERATION)\n"
    namespace: dict[str, Any] = {"Request": Request, "dispatch": dispatch, "OPERATION": operation}
    exec(source, namespace)  # Contract path names are validated identifiers, not request data.
    raw = namespace["endpoint"]
    raw.__name__ = operation.operation_id
    raw.__qualname__ = operation.operation_id
    return cast(
        Callable[..., Awaitable[JSONResponse | Response | dict[str, object] | list[dict[str, object]]]],
        raw,
    )


def _path_params(path: str) -> list[str]:
    names = _PARAM.findall(path)
    for name in names:
        if not name.isidentifier():
            raise ValueError(f"path parameter {name!r} is not a Python identifier")
    return names
