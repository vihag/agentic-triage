"""CROWN-001: a host is a crown-jewel asset. Blocks auto-close.

Effect when matched: ``never_auto_close``. The unmatched rationale for a single
host matches ``triage-decision.downgrade.json``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from triage_agent.contract import RuleResult, SeverityEffect, TriageContext
from triage_agent.results import matched, unmatched
from triage_agent.rules.fields import flag_is_true, host_record, hosts_of

_RULE_ID = "CROWN-001-crown-jewel-asset"
_VERSION = "1.0.0"


def crown_hosts(alert: Mapping[str, Any], ctx: TriageContext) -> list[str]:
    found: list[str] = []
    for host in hosts_of(alert):
        if flag_is_true(host_record(ctx, host).get("crown_jewel")):
            found.append(host)
    return found


class CrownJewelAsset:
    rule_id = _RULE_ID
    version = _VERSION
    priority = 10

    def applies_to(self, alert: Mapping[str, Any]) -> bool:
        return bool(hosts_of(alert))

    def evaluate(self, alert: Mapping[str, Any], ctx: TriageContext) -> RuleResult:
        hosts = hosts_of(alert)
        if not hosts:
            return unmatched(
                _RULE_ID, _VERSION, "Alert has no host to check for crown-jewel status."
            )
        jewels = crown_hosts(alert, ctx)
        if jewels:
            if len(jewels) == 1:
                rationale = f"{jewels[0]} is a crown-jewel asset."
            else:
                rationale = f"{', '.join(jewels)} are crown-jewel assets."
            return matched(
                _RULE_ID,
                _VERSION,
                SeverityEffect("never_auto_close"),
                rationale,
                labels=("guard:crown-jewel",),
            )
        if len(hosts) == 1:
            return unmatched(_RULE_ID, _VERSION, f"{hosts[0]} is not a crown-jewel asset.")
        return unmatched(_RULE_ID, _VERSION, f"{', '.join(hosts)} are not crown-jewel assets.")


RULE = CrownJewelAsset()
