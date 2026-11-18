"""auth.denied hook.

T05 owns the hash-chained audit_events write. This branch has no audit table,
so a bot approve/reject still returns 403 and the denial is handed to this hook
for T15 to persist.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Protocol

from app.principals import BotPrincipal

logger = logging.getLogger("agentic_triage.audit")


@dataclass(frozen=True)
class AuthDeniedNotice:
    """Facts for an AuditEvent with type auth.denied. seq and hash are T05's."""

    event_type: Literal["auth.denied"]
    actor: BotPrincipal
    operation_id: str
    instance: str
    case_id: str | None
    action_id: str | None


class AuditHook(Protocol):
    def record_auth_denied(self, notice: AuthDeniedNotice) -> None: ...


class LoggingAuditHook:
    """Records the denial on the process log. Does not write a database row."""

    def record_auth_denied(self, notice: AuthDeniedNotice) -> None:
        logger.info(
            "auth.denied operation_id=%s actor_id=%s on_behalf_of=%s instance=%s case_id=%s action_id=%s",
            notice.operation_id,
            notice.actor.id,
            notice.actor.on_behalf_of,
            notice.instance,
            notice.case_id,
            notice.action_id,
        )
