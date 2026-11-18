"""Register one route per OpenAPI operation.

healthz is implemented. approve and reject enforce the analyst-only guard.
Every other operation returns 501 after its auth scheme succeeds, including
botGetCaseBundle and listBotRuns. Building the bundle and listing runs is T16.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.auth import enforce
from app.problems import not_implemented
from app.spec import Operation

_PARAM = re.compile(r"\{([^{}]+)\}")


async def dispatch(request: Request, operation: Operation) -> JSONResponse | dict[str, str]:
    blocked = enforce(request, operation)
    if blocked is not None:
        return blocked
    if operation.operation_id == "healthz":
        return {"status": "ok"}
    return not_implemented(request, operation.operation_id)


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


def _endpoint(operation: Operation) -> Callable[..., Awaitable[JSONResponse | dict[str, str]]]:
    names = _path_params(operation.path)
    arguments = ", ".join(["request: Request", *(f"{name}: str" for name in names)])
    source = f"async def endpoint({arguments}):\n    return await dispatch(request, OPERATION)\n"
    namespace: dict[str, Any] = {"Request": Request, "dispatch": dispatch, "OPERATION": operation}
    exec(source, namespace)  # Contract path names are validated identifiers, not request data.
    raw = namespace["endpoint"]
    raw.__name__ = operation.operation_id
    raw.__qualname__ = operation.operation_id
    return cast(Callable[..., Awaitable[JSONResponse | dict[str, str]]], raw)


def _path_params(path: str) -> list[str]:
    names = _PARAM.findall(path)
    for name in names:
        if not name.isidentifier():
            raise ValueError(f"path parameter {name!r} is not a Python identifier")
    return names
