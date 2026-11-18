"""PRIV-002: a user is privileged. Raises severity by one level.

Effect when matched: ``delta`` +1. This is the whole effect named by T09;
``never_auto_close`` for privileged identities is not this rule.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from triage_agent.contract import RuleResult, SeverityEffect, TriageContext
from triage_agent.results import matched, unmatched
from triage_agent.rules.fields import flag_is_true, identity_record, users_of

_RULE_ID = "PRIV-002-privileged-user"
_VERSION = "1.0.0"


def privileged_users(alert: Mapping[str, Any], ctx: TriageContext) -> list[str]:
    found: list[str] = []
    for user in users_of(alert):
        if flag_is_true(identity_record(ctx, user).get("privileged")):
            found.append(user)
    return found


class PrivilegedUser:
    rule_id = _RULE_ID
    version = _VERSION
    priority = 20
    certainty = 0.8

    def applies_to(self, alert: Mapping[str, Any]) -> bool:
        return bool(users_of(alert))

    def evaluate(self, alert: Mapping[str, Any], ctx: TriageContext) -> RuleResult:
        users = users_of(alert)
        if not users:
            return unmatched(_RULE_ID, _VERSION, "Alert has no user to check for privilege.")
        privileged = privileged_users(alert, ctx)
        if privileged:
            if len(privileged) == 1:
                rationale = f"User {privileged[0]} is privileged (+1 severity)."
            else:
                rationale = f"Users {', '.join(privileged)} are privileged (+1 severity)."
            return matched(
                _RULE_ID,
                _VERSION,
                SeverityEffect("delta", delta=1),
                rationale,
                labels=("guard:privileged-user",),
            )
        if len(users) == 1:
            return unmatched(_RULE_ID, _VERSION, f"User {users[0]} is not privileged.")
        return unmatched(_RULE_ID, _VERSION, f"Users {', '.join(users)} are not privileged.")


RULE = PrivilegedUser()
