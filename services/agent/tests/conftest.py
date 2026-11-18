"""Shared fixtures. Example alerts are contract files; counts come from the webhook."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from triage_agent.contract import TriageContext
from triage_agent.engine import RuleEngine

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "contracts" / "examples"
SCHEMAS = REPO / "contracts" / "schemas"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text())


@pytest.fixture(scope="session")
def engine() -> RuleEngine:
    return RuleEngine()


@pytest.fixture
def escalate_alert() -> dict:
    """Alert example with the verbatim Splunk webhook as ``raw`` (schema contract)."""
    alert = load_example("alert.escalate.json")
    alert["raw"] = load_example("splunk-webhook.escalate.json")
    return alert


@pytest.fixture
def downgrade_alert() -> dict:
    alert = load_example("alert.downgrade.json")
    alert["raw"] = load_example("splunk-webhook.downgrade.json")
    return alert


@pytest.fixture
def ci_context() -> TriageContext:
    return TriageContext(
        asset_inventory={"build-agent-07": {"crown_jewel": False, "group": "ci-build-agents"}}
    )


@pytest.fixture(scope="session")
def decision_validator() -> Draft202012Validator:
    registry: Registry = Registry()
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        contents = json.loads(path.read_text())
        resource = Resource.from_contents(contents, default_specification=DRAFT202012)
        registry = registry.with_resource(path.name, resource)
    return Draft202012Validator(
        {"$ref": "triage-decision.schema.json"},
        registry=registry,
        format_checker=FormatChecker(),
    )
