"""AUTH-003: failures then a success from a non-corporate IP, within 10 minutes.

Effect when matched: floor at high, label ``candidate:credential-stuffing``.
The matched rationale matches ``triage-decision.escalate.json``.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from typing import Any

from triage_agent.contract import RuleResult, SeverityEffect, TriageContext
from triage_agent.results import matched, unmatched
from triage_agent.rules.fields import (
    allow_values,
    failure_success_counts,
    ip_in_list,
    search_name,
    src_ips_of,
    title_text,
    users_of,
    window_minutes,
)

_RULE_ID = "AUTH-003-fail-then-success-external"
_VERSION = "1.2.0"
_WINDOW_MINUTES = 10


def _phrase(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def mentions_fail_then_success(alert: Mapping[str, Any]) -> bool:
    blob = f"{search_name(alert)} {title_text(alert)}".lower()
    return "fail" in blob and "success" in blob


def is_nonroutable(ip: str) -> bool:
    """RFC1918, loopback, link-local, and IPv6 unique-local.

    Documentation space such as 203.0.113.0/24 is routable here on purpose:
    Python's ``ipaddress`` treats that range as private, but the escalate
    example calls 203.0.113.45 a non-corporate source.
    """
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return False
    if addr.is_loopback or addr.is_link_local:
        return True
    if isinstance(addr, ipaddress.IPv6Address):
        return addr in ipaddress.ip_network("fc00::/7")
    if addr in ipaddress.ip_network("10.0.0.0/8"):
        return True
    if addr in ipaddress.ip_network("172.16.0.0/12"):
        return True
    return addr in ipaddress.ip_network("192.168.0.0/16")


def is_corporate_ip(ip: str, ctx: TriageContext) -> bool:
    """True when the IP is on the corporate allow-list or is non-routable.

    The allow-list adds public corporate egress. It does not remove RFC1918.
    """
    listed = allow_values(ctx, "corporate_ips", "corporate-ips", "corporate_cidrs")
    if listed and ip_in_list(ip, listed):
        return True
    return is_nonroutable(ip)


class FailThenSuccessExternal:
    rule_id = _RULE_ID
    version = _VERSION
    priority = 30

    def applies_to(self, alert: Mapping[str, Any]) -> bool:
        if mentions_fail_then_success(alert):
            return True
        failed, success = failure_success_counts(alert)
        return failed is not None and success is not None

    def evaluate(self, alert: Mapping[str, Any], ctx: TriageContext) -> RuleResult:
        failed, success = failure_success_counts(alert)
        if failed is None or success is None:
            return unmatched(_RULE_ID, _VERSION, "Failure and success counts are missing.")
        if failed < 1 or success < 1:
            return unmatched(_RULE_ID, _VERSION, "Need at least one failure and one success.")
        if len(users_of(alert)) != 1:
            return unmatched(_RULE_ID, _VERSION, "Fail-then-success must be for a single user.")
        external = [ip for ip in src_ips_of(alert) if not is_corporate_ip(ip, ctx)]
        if not external:
            return unmatched(_RULE_ID, _VERSION, "Source IP is missing or corporate.")
        window = window_minutes(alert)
        if window is None:
            if not mentions_fail_then_success(alert):
                return unmatched(_RULE_ID, _VERSION, "No 10 minute window on this alert.")
        elif window <= 0 or window > _WINDOW_MINUTES:
            return unmatched(
                _RULE_ID,
                _VERSION,
                f"Window of {window} minutes is outside the 10 minute limit.",
            )
        rationale = (
            f"{_phrase(failed, 'failure', 'failures')} then "
            f"{_phrase(success, 'success', 'successes')} "
            "for the same user from a non-corporate IP within 10 minutes."
        )
        return matched(
            _RULE_ID,
            _VERSION,
            SeverityEffect("floor", "high"),
            rationale,
            labels=("candidate:credential-stuffing",),
            evidence_refs=("ev-raw-1",),
        )


RULE = FailThenSuccessExternal()
