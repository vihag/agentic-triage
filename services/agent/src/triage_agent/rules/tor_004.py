"""TOR-004: traffic to a TOR exit, or an alert the search already called TOR.

Effect when matched: floor at high, label ``candidate:tor-egress``. A Splunk
high that only meets this floor stays high (the unchanged-high scenario).
Exit nodes come from the injected allow-list, never from the network.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from triage_agent.contract import RuleResult, SeverityEffect, TriageContext
from triage_agent.results import matched, unmatched
from triage_agent.rules.fields import (
    allow_values,
    description_text,
    dest_ips_of,
    domains_of,
    ip_in_list,
    search_name,
    signature_of,
    title_text,
)

_RULE_ID = "TOR-004-tor-egress"
_VERSION = "1.0.0"
_TOR = re.compile(r"\btor\b", re.IGNORECASE)
_LISTS = ("tor_exit_nodes", "tor_exits", "tor-exit-nodes")


def mentions_tor(alert: Mapping[str, Any]) -> bool:
    blob = " ".join(
        (
            search_name(alert),
            title_text(alert),
            description_text(alert),
            signature_of(alert),
        )
    )
    return _TOR.search(blob) is not None


def domain_listed(domain: str, patterns: Sequence[str]) -> bool:
    candidate = domain.strip().lower().rstrip(".")
    if not candidate:
        return False
    for pattern in patterns:
        text = pattern.strip().lower().rstrip(".")
        if not text or "/" in text:
            continue
        if candidate == text or candidate.endswith("." + text):
            return True
    return False


class TorEgress:
    rule_id = _RULE_ID
    version = _VERSION
    priority = 40

    def applies_to(self, alert: Mapping[str, Any]) -> bool:
        if dest_ips_of(alert) or domains_of(alert):
            return True
        return mentions_tor(alert)

    def evaluate(self, alert: Mapping[str, Any], ctx: TriageContext) -> RuleResult:
        exits = allow_values(ctx, *_LISTS)
        hit_ips = [ip for ip in dest_ips_of(alert) if ip_in_list(ip, exits)]
        hit_domains = [domain for domain in domains_of(alert) if domain_listed(domain, exits)]
        if hit_ips:
            rationale = f"Destination {hit_ips[0]} is a TOR exit node."
        elif hit_domains:
            rationale = f"Destination {hit_domains[0]} is a TOR exit node."
        elif mentions_tor(alert):
            rationale = "Alert indicates TOR egress."
        else:
            return unmatched(_RULE_ID, _VERSION, "Destination is not a known TOR exit node.")
        return matched(
            _RULE_ID,
            _VERSION,
            SeverityEffect("floor", "high"),
            rationale,
            labels=("candidate:tor-egress",),
            evidence_refs=("ev-raw-1",),
        )


RULE = TorEgress()
