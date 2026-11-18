"""analystAuth (JWT), botApiKey, and splunkToken.

Demo analyst tokens are HS256 signed with JWT_SECRET. The architecture's IdP
JWKS adapter is the same AnalystTokenVerifier protocol; this process does not
call an identity provider. CI never calls a model or an IdP.
"""

from __future__ import annotations

import secrets
import time
from enum import Enum
from typing import Literal, Protocol, assert_never

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from jwt import InvalidTokenError

from app.audit import AuditHook, AuthDeniedNotice
from app.principals import (
    AnalystPrincipal,
    BotPrincipal,
    Principal,
    PublicPrincipal,
    SplunkPrincipal,
)
from app.problems import forbidden_bot, unauthorized
from app.settings import Settings
from app.spec import (
    ANALYST_AUTH,
    APPROVAL_OPERATION_IDS,
    Operation,
)

AuthScheme = Literal["analystAuth", "botApiKey", "splunkToken"]


class AnalystTokenVerifier(Protocol):
    def verify(self, token: str) -> AnalystPrincipal | None: ...


class HmacJwtVerifier:
    """Verify demo JWTs. Algorithm is fixed to HS256; the token header cannot select it."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def verify(self, token: str) -> AnalystPrincipal | None:
        try:
            payload = jwt.decode(
                token,
                self._settings.jwt_secret,
                algorithms=["HS256"],
                audience=self._settings.jwt_audience,
                issuer=self._settings.jwt_issuer,
                options={"require": ["exp", "sub", "iss", "aud"]},
            )
        except InvalidTokenError:
            return None
        subject = payload.get("sub")
        if not isinstance(subject, str) or subject.strip() == "":
            return None
        name = payload.get("name")
        display_name = name if isinstance(name, str) and name else None
        return AnalystPrincipal(id=subject, display_name=display_name)


def mint_analyst_token(
    settings: Settings,
    analyst_id: str,
    *,
    display_name: str | None = None,
    ttl_seconds: int = 3600,
    now: int | None = None,
) -> str:
    if not analyst_id or ttl_seconds <= 0:
        raise ValueError("analyst_id and a positive ttl are required")
    issued = int(time.time()) if now is None else now
    claims: dict[str, object] = {
        "sub": analyst_id,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": issued,
        "exp": issued + ttl_seconds,
    }
    if display_name is not None:
        claims["name"] = display_name
    token = jwt.encode(claims, settings.jwt_secret, algorithm="HS256")
    if isinstance(token, bytes):
        return token.decode("ascii")
    return token


class ApprovalResult(Enum):
    ALLOW = "allow"
    DENY_BOT = "deny_bot"
    UNAUTHENTICATED = "unauthenticated"


def approval_guard(bot: BotPrincipal | None, analyst: AnalystPrincipal | None) -> ApprovalResult:
    """Analysts may decide. A resolved bot key is refused even if a JWT is also present."""

    if bot is not None:
        return ApprovalResult.DENY_BOT
    if analyst is None:
        return ApprovalResult.UNAUTHENTICATED
    return ApprovalResult.ALLOW


def enforce(request: Request, operation: Operation) -> JSONResponse | None:
    """Return a problem response, or None after storing request.state.principal."""

    settings: Settings = request.app.state.settings
    if operation.operation_id in APPROVAL_OPERATION_IDS:
        return _enforce_approval(request, operation, settings)
    principal = _authenticate(request, operation, settings)
    if isinstance(principal, JSONResponse):
        return principal
    request.state.principal = principal
    return None


def _enforce_approval(request: Request, operation: Operation, settings: Settings) -> JSONResponse | None:
    bot = resolve_bot(request, settings)
    analyst = resolve_analyst(request, settings)
    decision = approval_guard(bot, analyst)
    match decision:
        case ApprovalResult.DENY_BOT:
            if bot is None:
                raise RuntimeError("bot denial without a bot principal")
            hook: AuditHook = request.app.state.audit
            hook.record_auth_denied(
                AuthDeniedNotice(
                    event_type="auth.denied",
                    actor=bot,
                    operation_id=operation.operation_id,
                    instance=request.url.path,
                    case_id=_path_param(request, "case_id"),
                    action_id=_path_param(request, "action_id"),
                )
            )
            return forbidden_bot(request)
        case ApprovalResult.UNAUTHENTICATED:
            return unauthorized(request, bearer_challenge=True)
        case ApprovalResult.ALLOW:
            if analyst is None:
                raise RuntimeError("approval allowed without an analyst principal")
            request.state.principal = analyst
            return None
        case _ as unreachable:
            assert_never(unreachable)


def _authenticate(request: Request, operation: Operation, settings: Settings) -> Principal | JSONResponse:
    if not operation.security:
        return PublicPrincipal()
    failure: JSONResponse | None = None
    for alternative in operation.security:
        result = _satisfy_all(request, alternative, settings)
        if not isinstance(result, JSONResponse):
            return result
        failure = result
    if failure is None:
        return unauthorized(request, bearer_challenge=False)
    return failure


def _satisfy_all(
    request: Request, schemes: tuple[str, ...], settings: Settings
) -> Principal | JSONResponse:
    if not schemes:
        return PublicPrincipal()
    resolved: Principal | None = None
    for scheme in schemes:
        principal = _resolve_scheme(scheme, request, settings)
        if principal is None:
            return unauthorized(request, bearer_challenge=scheme == ANALYST_AUTH)
        resolved = principal
    if resolved is None:
        return PublicPrincipal()
    return resolved


_SCHEMES: dict[str, AuthScheme] = {
    "analystAuth": "analystAuth",
    "botApiKey": "botApiKey",
    "splunkToken": "splunkToken",
}


def _as_scheme(scheme: str) -> AuthScheme:
    known = _SCHEMES.get(scheme)
    if known is None:
        raise RuntimeError(f"unsupported security scheme {scheme}")
    return known


def _resolve_scheme(scheme: str, request: Request, settings: Settings) -> Principal | None:
    known = _as_scheme(scheme)
    match known:
        case "analystAuth":
            return resolve_analyst(request, settings)
        case "botApiKey":
            return resolve_bot(request, settings)
        case "splunkToken":
            return resolve_splunk(request, settings)
        case _ as unreachable:
            assert_never(unreachable)


def resolve_analyst(request: Request, settings: Settings) -> AnalystPrincipal | None:
    token = _bearer(request)
    if token is None:
        return None
    return HmacJwtVerifier(settings).verify(token)


def resolve_bot(request: Request, settings: Settings) -> BotPrincipal | None:
    presented = request.headers.get("X-GrokBot-Key")
    if presented is None or presented == "":
        return None
    identity = settings.bot_keys.resolve(presented)
    if identity is None:
        return None
    return BotPrincipal(id=identity.bot_id, on_behalf_of=identity.on_behalf_of)


def resolve_splunk(request: Request, settings: Settings) -> SplunkPrincipal | None:
    presented = request.query_params.get("token")
    expected = settings.splunk_webhook_token
    if presented is None or not expected:
        return None
    if not secrets_equal(presented, expected):
        return None
    instance = _path_param(request, "instance")
    return SplunkPrincipal(id=instance if instance is not None else "splunk")


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header is None:
        return None
    scheme, separator, token = header.partition(" ")
    if separator == "" or scheme.lower() != "bearer":
        return None
    stripped = token.strip()
    if not stripped:
        return None
    return stripped


def _path_param(request: Request, name: str) -> str | None:
    value = request.path_params.get(name)
    if isinstance(value, str) and value:
        return value
    return None


def secrets_equal(left: str, right: str) -> bool:
    return secrets.compare_digest(left.encode(), right.encode())
