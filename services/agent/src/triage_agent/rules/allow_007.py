"""ALLOW-007: source IP is on the known-scanner allow-list.

Effect when matched: ceiling at low, label ``benign:known-scanner``.
The unmatched rationale matches ``triage-decision.escalate.json``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from triage_agent.contract import RuleResult, SeverityEffect, TriageContext
from triage_agent.results import matched, unmatched
from triage_agent.rules.fields import allow_values, ip_in_list, src_ips_of

_RULE_ID = "ALLOW-007-known-scanner"
_VERSION = "1.0.0"


class KnownScanner:
    rule_id = _RULE_ID
    version = _VERSION
    priority = 70
    certainty = 0.8

    def applies_to(self, alert: Mapping[str, Any]) -> bool:
        return bool(src_ips_of(alert))

    def evaluate(self, alert: Mapping[str, Any], ctx: TriageContext) -> RuleResult:
        ips = src_ips_of(alert)
        if not ips:
            return unmatched(
                _RULE_ID,
                _VERSION,
                "Alert has no source IP to check against the scanner allow-list.",
            )
        scanners = allow_values(ctx, "scanners", "scanner_ips", "known_scanners")
        hits = [ip for ip in ips if ip_in_list(ip, scanners)]
        if not hits:
            return unmatched(_RULE_ID, _VERSION, "Source IP not in scanner allow-list.")
        return matched(
            _RULE_ID,
            _VERSION,
            SeverityEffect("ceiling", "low"),
            f"Source IP {hits[0]} is in the scanner allow-list.",
            labels=("benign:known-scanner",),
        )


RULE = KnownScanner()
