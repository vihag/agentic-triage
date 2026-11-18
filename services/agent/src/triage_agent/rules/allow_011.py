"""ALLOW-011: EICAR test file on a host in the CI build-agent asset group.

Effect when matched: ceiling at low, label ``benign:av-selftest``.
The matched rationale matches ``triage-decision.downgrade.json``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from triage_agent.contract import RuleResult, SeverityEffect, TriageContext
from triage_agent.results import matched, unmatched
from triage_agent.rules.fields import (
    description_text,
    file_hashes_of,
    host_record,
    hosts_of,
    search_name,
    signature_of,
    title_text,
)

_RULE_ID = "ALLOW-011-eicar-on-ci"
_VERSION = "1.0.0"
_MATCHED = "EICAR test hash on a host in the CI build-agent asset group."

# EICAR standard hashes: SHA-256, MD5, SHA-1.
EICAR_HASHES = frozenset(
    {
        "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f",
        "44d88612fea8a8f36de82e1278abb02f",
        "3395856ce81f2b7382dee72602f798b642f14140",
    }
)


def is_ci_build_group(group: object) -> bool:
    if not isinstance(group, str):
        return False
    normalised = group.strip().lower().replace("_", "-").replace(" ", "-")
    if not normalised:
        return False
    return "ci-build" in normalised or "build-agent" in normalised


def is_eicar(alert: Mapping[str, Any]) -> bool:
    if any(item in EICAR_HASHES for item in file_hashes_of(alert)):
        return True
    if "eicar" in signature_of(alert).lower():
        return True
    blob = f"{title_text(alert)} {description_text(alert)}".lower()
    return "eicar" in blob


def ci_hosts(alert: Mapping[str, Any], ctx: TriageContext) -> list[str]:
    found: list[str] = []
    for host in hosts_of(alert):
        group = host_record(ctx, host).get("group")
        if is_ci_build_group(group):
            found.append(host)
    return found


class EicarOnCi:
    rule_id = _RULE_ID
    version = _VERSION
    priority = 110

    def applies_to(self, alert: Mapping[str, Any]) -> bool:
        if file_hashes_of(alert) or signature_of(alert):
            return True
        blob = f"{search_name(alert)} {title_text(alert)}".lower()
        return "malware" in blob or "eicar" in blob

    def evaluate(self, alert: Mapping[str, Any], ctx: TriageContext) -> RuleResult:
        eicar = is_eicar(alert)
        hosts = ci_hosts(alert, ctx)
        if eicar and hosts:
            return matched(
                _RULE_ID,
                _VERSION,
                SeverityEffect("ceiling", "low"),
                _MATCHED,
                labels=("benign:av-selftest",),
                evidence_refs=("ev-raw-1",),
            )
        if eicar:
            return unmatched(
                _RULE_ID,
                _VERSION,
                "EICAR test hash is present but no host is in the CI build-agent asset group.",
            )
        if hosts:
            return unmatched(
                _RULE_ID,
                _VERSION,
                "Host is in the CI build-agent asset group but the file is not the EICAR test.",
            )
        return unmatched(_RULE_ID, _VERSION, "Not an EICAR test hash on a CI build-agent.")


RULE = EicarOnCi()
