"""Splunk normaliser matches contract alerts (ids/timestamps aside)."""

from __future__ import annotations

import json
from pathlib import Path

from app.splunk_normalize import normalize_splunk_webhook

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "contracts" / "examples"


def _load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text())


def _without_generated(alert: dict) -> dict:
    return {key: value for key, value in alert.items() if key not in {"alert_id", "received_at", "raw"}}


def test_escalate_example_fields() -> None:
    webhook = _load("splunk-webhook.escalate.json")
    expected = _load("alert.escalate.json")
    got = normalize_splunk_webhook(
        webhook,
        instance="splunk-onprem-sg1",
        query_severity=None,
        received_at=expected["received_at"],
    )
    assert got["event_time"] == expected["event_time"]
    assert got["raw"] == webhook
    assert _without_generated(got) == _without_generated(expected)


def test_downgrade_example_fields() -> None:
    webhook = _load("splunk-webhook.downgrade.json")
    expected = _load("alert.downgrade.json")
    got = normalize_splunk_webhook(
        webhook,
        instance="splunk-onprem-sg1",
        query_severity=None,
        received_at=expected["received_at"],
    )
    assert got["raw"] == webhook
    for key, value in _without_generated(expected).items():
        if key == "source":
            for subkey, subvalue in value.items():
                assert got["source"][subkey] == subvalue
            continue
        assert got[key] == value


def test_query_severity_overrides_result() -> None:
    webhook = _load("splunk-webhook.escalate.json")
    got = normalize_splunk_webhook(webhook, instance="sg1", query_severity=6, received_at="2026-11-18T00:00:00Z")
    assert got["splunk_severity"] == "critical"