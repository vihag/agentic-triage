"""Named Splunk webhook scenarios and the burst recipe.

Named scenarios are the raw JSON files in ``simulator.scenarios``. Burst mode
copies those bytes and replaces the template ``sid`` (the same text also sits
in ``results_link``) so each alert is a distinct ingest idempotency key.

The burst mix is the L3 demo in ``docs/testing.md``: 10 alerts, 7 noise,
2 escalations, 1 unchanged-high.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from importlib.resources import files

from simulator.errors import SimulatorError

SidFactory = Callable[[int, str], str]

# docs/testing.md: simulator burst is 10 alerts.
BURST_SIZE = 10
_SID_RE = re.compile(r"^[A-Za-z0-9_]{1,200}$")
_OUTCOMES = frozenset({"escalate", "downgrade", "unchanged-high", "unchanged-low"})


@dataclass(frozen=True)
class Scenario:
    """One saved Splunk alert the simulator can POST."""

    name: str
    outcome: str
    summary: str
    filename: str
    aliases: tuple[str, ...] = ()
    # Set when this file is a byte copy of a frozen contract example.
    contract_example: str | None = None

    def read_bytes(self) -> bytes:
        return files("simulator.scenarios").joinpath(self.filename).read_bytes()


@dataclass(frozen=True)
class WebhookMessage:
    """One webhook body ready to POST. ``body`` is the exact request entity."""

    scenario: str
    outcome: str
    body: bytes
    sid: str
    severity: int | None


SCENARIOS: dict[str, Scenario] = {
    "credential-stuffing": Scenario(
        name="credential-stuffing",
        outcome="escalate",
        summary="Failed logins followed by a success from an external IP.",
        filename="credential-stuffing.json",
        aliases=("escalate", "credential stuffing"),
        contract_example="splunk-webhook.escalate.json",
    ),
    "eicar-on-ci": Scenario(
        name="eicar-on-ci",
        outcome="downgrade",
        summary="EICAR test file on a CI build agent.",
        filename="eicar-on-ci.json",
        aliases=("downgrade", "eicar", "eicar on ci"),
        contract_example="splunk-webhook.downgrade.json",
    ),
    "tor-egress": Scenario(
        name="tor-egress",
        outcome="unchanged-high",
        summary="High-severity outbound connection to a TOR exit node.",
        filename="tor-egress.json",
        aliases=("unchanged-high", "tor", "tor egress"),
    ),
    "noisy-port-scan": Scenario(
        name="noisy-port-scan",
        outcome="unchanged-low",
        summary="Low-severity external port scan (noise).",
        filename="noisy-port-scan.json",
        aliases=("unchanged-low", "port scan", "noisy port scan"),
    ),
}

# Order is the order `simulator send burst` posts.
BURST_RECIPE: tuple[tuple[str, int], ...] = (
    ("credential-stuffing", 2),
    ("tor-egress", 1),
    ("noisy-port-scan", 7),
)


def _check_catalog() -> None:
    total = 0
    for name, count in BURST_RECIPE:
        if name not in SCENARIOS:
            raise RuntimeError(f"burst recipe names unknown scenario {name}")
        if count < 1:
            raise RuntimeError(f"burst recipe count for {name} must be positive")
        total += count
    if total != BURST_SIZE:
        raise RuntimeError(f"burst recipe sums to {total}, expected {BURST_SIZE}")
    for scenario in SCENARIOS.values():
        if scenario.outcome not in _OUTCOMES:
            raise RuntimeError(f"{scenario.name} has unknown outcome {scenario.outcome}")


_check_catalog()


def _normalize(name: str) -> str:
    return " ".join(name.strip().lower().replace("_", " ").replace("-", " ").split())


def _build_alias_index() -> dict[str, str]:
    index: dict[str, str] = {}

    def add(alias: str, canonical: str) -> None:
        key = _normalize(alias)
        current = index.get(key)
        if current is not None and current != canonical:
            raise RuntimeError(f"alias {alias!r} maps to both {current} and {canonical}")
        index[key] = canonical

    for scenario in SCENARIOS.values():
        add(scenario.name, scenario.name)
        for alias in scenario.aliases:
            add(alias, scenario.name)
    add("burst", "burst")
    add("burst mode", "burst")
    return index


_ALIASES = _build_alias_index()


def known_names() -> tuple[str, ...]:
    """Canonical scenario names, with ``burst`` last."""
    return (*SCENARIOS.keys(), "burst")


def resolve_scenario(name: str) -> str:
    """Map a CLI name or alias to a canonical scenario, or ``burst``."""
    canonical = _ALIASES.get(_normalize(name))
    if canonical is None:
        known = ", ".join(known_names())
        raise SimulatorError(f"unknown scenario {name!r}. Known: {known}")
    return canonical


def _severity(payload: dict) -> int | None:
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    severity = result.get("severity")
    if isinstance(severity, str) and severity in {"1", "2", "3", "4", "5", "6"}:
        return int(severity)
    return None


def _message(scenario: Scenario, body: bytes) -> WebhookMessage:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SimulatorError(f"{scenario.name}: scenario file is not JSON ({exc})") from exc
    sid = payload.get("sid") if isinstance(payload, dict) else None
    if not isinstance(sid, str) or sid == "":
        raise SimulatorError(f"{scenario.name}: scenario file is missing sid")
    return WebhookMessage(
        scenario=scenario.name,
        outcome=scenario.outcome,
        body=body,
        sid=sid,
        severity=_severity(payload),
    )


def _replace_sid(body: bytes, new_sid: str) -> bytes:
    """Replace the template sid text in place. The surrounding bytes stay put."""
    if _SID_RE.fullmatch(new_sid) is None:
        raise SimulatorError(f"refusing sid that is not a Splunk-safe token: {new_sid!r}")
    payload = json.loads(body)
    old = payload.get("sid")
    if not isinstance(old, str) or old == "":
        raise SimulatorError("scenario template is missing sid")
    try:
        old_b = old.encode("ascii")
    except UnicodeEncodeError as exc:
        raise SimulatorError(f"template sid is not ASCII: {old!r}") from exc
    if old_b not in body:
        raise SimulatorError("sid value is not present in the template bytes")
    updated = body.replace(old_b, new_sid.encode("ascii"))
    parsed = json.loads(updated)
    if parsed.get("sid") != new_sid:
        raise SimulatorError("sid replacement did not update the sid field")
    old_link = payload.get("results_link")
    new_link = parsed.get("results_link")
    if isinstance(old_link, str) and old in old_link:
        if not isinstance(new_link, str) or new_sid not in new_link:
            raise SimulatorError("results_link was not updated with the new sid")
    return updated


def _default_sid(index: int, scenario: str) -> str:
    slug = scenario.replace("-", "_")
    return f"scheduler__admin__simulator__{slug}_{time.time_ns()}_{index:02d}"


def _burst(sid_factory: SidFactory) -> tuple[WebhookMessage, ...]:
    messages: list[WebhookMessage] = []
    index = 0
    for scenario_name, count in BURST_RECIPE:
        scenario = SCENARIOS[scenario_name]
        template = scenario.read_bytes()
        for _ in range(count):
            body = _replace_sid(template, sid_factory(index, scenario_name))
            messages.append(_message(scenario, body))
            index += 1
    sids = [message.sid for message in messages]
    if len(sids) != len(set(sids)):
        raise SimulatorError("burst generated duplicate sids")
    if len(messages) != BURST_SIZE:
        raise SimulatorError(f"burst must emit {BURST_SIZE} alerts, got {len(messages)}")
    return tuple(messages)


def iter_messages(name: str, *, sid_factory: SidFactory | None = None) -> tuple[WebhookMessage, ...]:
    """Webhook bodies for ``name``.

    A named scenario returns the file bytes unchanged. ``burst`` returns
    ``BURST_SIZE`` messages with unique sids. ``sid_factory`` is only used
    for burst; tests pass a fixed factory.
    """
    canonical = resolve_scenario(name)
    if canonical == "burst":
        return _burst(sid_factory or _default_sid)
    return (_message(SCENARIOS[canonical], SCENARIOS[canonical].read_bytes()),)
