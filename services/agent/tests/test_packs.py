"""Pack builders emit schema-shaped documents."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from triage_agent.packs import build_evidence_pack, build_next_steps_pack

REPO = Path(__file__).resolve().parents[3]
SCHEMAS = REPO / "contracts" / "schemas"


def _validator(name: str) -> Draft202012Validator:
    registry: Registry = Registry()
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        contents = json.loads(path.read_text())
        registry = registry.with_resource(
            path.name,
            Resource.from_contents(contents, default_specification=DRAFT202012),
        )
    schema = json.loads((SCHEMAS / name).read_text())
    return Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())


def test_template_packs_validate() -> None:
    alert = {
        "alert_id": "11111111-1111-4111-8111-111111111111",
        "title": "Example",
        "entities": {"users": ["jdoe"]},
        "source": {"search_name": "Excessive Failed Logins Followed By Success", "sid": "sid"},
        "raw": {"result": {"user": "jdoe"}},
    }
    decision = {
        "policy": {"rationale": "Escalated"},
        "rule_results": [{"rule_id": "AUTH-003", "matched": True}],
        "fuzzy_result": None,
    }
    case_id = "22222222-2222-4222-8222-222222222222"
    evidence = build_evidence_pack(case_id=case_id, alert=alert, decision=decision)
    steps, actions = build_next_steps_pack(case_id=case_id, alert=alert, decision=decision)
    assert list(_validator("evidence-pack.schema.json").iter_errors(evidence)) == []
    assert list(_validator("next-steps-pack.schema.json").iter_errors(steps)) == []
    assert actions[0]["status"] == "proposed"
    assert actions[0]["requires_approval"] is True