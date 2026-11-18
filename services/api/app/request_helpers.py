"""Shared request parsing for case mutations."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from app.principals import (
    AnalystPrincipal,
    BotPrincipal,
    Principal,
    PublicPrincipal,
    SplunkPrincipal,
)


def parse_if_match(request: Request) -> int | None:
    raw = request.headers.get("If-Match")
    if raw is None or raw == "":
        return None
    stripped = raw.strip().strip('"').strip("'")
    if stripped.startswith("W/"):
        stripped = stripped[2:].strip().strip('"').strip("'")
    try:
        return int(stripped)
    except ValueError:
        return None


def actor_from_request(request: Request) -> dict[str, Any]:
    principal: Principal = request.state.principal
    match principal:
        case AnalystPrincipal():
            actor: dict[str, Any] = {"type": "analyst", "id": principal.id}
            if principal.display_name:
                actor["display_name"] = principal.display_name
            return actor
        case BotPrincipal():
            actor = {"type": "grok_bot", "id": principal.id}
            if principal.on_behalf_of:
                actor["on_behalf_of"] = principal.on_behalf_of
            return actor
        case SplunkPrincipal():
            return {"type": "splunk", "id": principal.id}
        case PublicPrincipal():
            return {"type": "system", "id": "api"}
        case _:
            return {"type": "system", "id": "api"}


def etag_for_version(version: int) -> str:
    return str(version)