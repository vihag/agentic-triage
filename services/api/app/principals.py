"""Callers resolved from the three OpenAPI security schemes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AnalystPrincipal:
    """Human analyst. The only principal that may approve or reject."""

    id: str
    display_name: str | None = None
    type: Literal["analyst"] = "analyst"


@dataclass(frozen=True)
class BotPrincipal:
    """Grok Bot key resolved to bot_id plus the analyst it acts for."""

    id: str
    on_behalf_of: str
    type: Literal["grok_bot"] = "grok_bot"


@dataclass(frozen=True)
class SplunkPrincipal:
    """Splunk webhook caller. id is the instance path segment."""

    id: str
    type: Literal["splunk"] = "splunk"


@dataclass(frozen=True)
class PublicPrincipal:
    """Operation declared security: [] (healthz)."""

    type: Literal["public"] = "public"


Principal = AnalystPrincipal | BotPrincipal | SplunkPrincipal | PublicPrincipal
