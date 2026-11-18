"""RFC 9457 problem details. Every error response uses application/problem+json."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_MEDIA_TYPE = "application/problem+json"
TYPE_BASE = "https://agentic-triage.local/problems/"

_TITLES = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    412: "Precondition Failed",
    422: "Unprocessable Entity",
    500: "Internal Server Error",
    501: "Not Implemented",
}

_TYPES = {
    401: TYPE_BASE + "unauthorized",
    403: TYPE_BASE + "forbidden",
    404: TYPE_BASE + "not-found",
    405: TYPE_BASE + "method-not-allowed",
    422: TYPE_BASE + "validation",
    501: TYPE_BASE + "not-implemented",
}

UNAUTHORIZED_DETAIL = "Missing or invalid credentials."
FORBIDDEN_BOT_DETAIL = "Bot credentials cannot approve or reject actions."


def problem(
    *,
    status: int,
    title: str | None = None,
    detail: str | None = None,
    instance: str | None = None,
    type_: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": type_ if type_ is not None else _TYPES.get(status, "about:blank"),
        "title": title if title is not None else _TITLES.get(status, "Error"),
        "status": status,
    }
    if detail is not None:
        body["detail"] = detail
    if instance is not None:
        body["instance"] = instance
    response = JSONResponse(status_code=status, content=body, media_type=PROBLEM_MEDIA_TYPE)
    if headers:
        for key, value in headers.items():
            response.headers[key] = value
    return response


def unauthorized(request: Request, *, bearer_challenge: bool) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if bearer_challenge else None
    return problem(
        status=401,
        detail=UNAUTHORIZED_DETAIL,
        instance=request.url.path,
        headers=headers,
    )


def forbidden_bot(request: Request) -> JSONResponse:
    return problem(status=403, detail=FORBIDDEN_BOT_DETAIL, instance=request.url.path)


def not_found(request: Request, detail: str) -> JSONResponse:
    return problem(status=404, detail=detail, instance=request.url.path)


def conflict(request: Request, detail: str) -> JSONResponse:
    return problem(status=409, detail=detail, instance=request.url.path)


def precondition_failed(request: Request, *, detail: str) -> JSONResponse:
    return problem(status=412, detail=detail, instance=request.url.path)


def not_implemented(request: Request, operation_id: str) -> JSONResponse:
    return problem(
        status=501,
        detail=f"{operation_id} is not implemented.",
        instance=request.url.path,
    )


def validation_problem(request: Request, exc: RequestValidationError) -> JSONResponse:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(item) for item in err.get("loc", ()))
        msg = str(err.get("msg", "invalid"))
        parts.append(f"{loc}: {msg}" if loc else msg)
    return problem(
        status=422,
        detail="; ".join(parts) if parts else "Invalid request.",
        instance=request.url.path,
    )


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        extra: dict[str, str] = {}
        if exc.headers:
            for key, value in exc.headers.items():
                if key.lower() != "content-type":
                    extra[key] = value
        return problem(status=exc.status_code, detail=detail, instance=request.url.path, headers=extra or None)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return validation_problem(request, exc)

    @app.exception_handler(RuntimeError)
    async def handle_runtime(request: Request, exc: RuntimeError) -> JSONResponse:
        message = str(exc)
        if "DATABASE_URL" in message:
            return problem(status=500, detail=message, instance=request.url.path)
        raise exc

    @app.exception_handler(OperationalError)
    async def handle_db_operational(request: Request, exc: OperationalError) -> JSONResponse:
        return problem(status=500, detail="Database unavailable.", instance=request.url.path)
