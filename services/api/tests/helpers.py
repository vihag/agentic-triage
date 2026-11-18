from __future__ import annotations

import re
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = REPO_ROOT / "contracts" / "openapi.yaml"

CASE_ID = "22222222-2222-4222-8222-222222222222"
ACTION_ID = "33333333-3333-4333-8333-333333333333"
_SAMPLES = {
    "instance": "splunk-prod",
    "alert_id": "11111111-1111-4111-8111-111111111111",
    "case_id": CASE_ID,
    "action_id": ACTION_ID,
    "run_id": "44444444-4444-4444-8444-444444444444",
}


def fill_path(path: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in _SAMPLES:
            raise AssertionError(f"no sample for path param {name}")
        return _SAMPLES[name]

    return re.sub(r"\{([^{}]+)\}", replace, path)


def assert_problem(response, validator: Draft202012Validator, status: int) -> dict:
    assert response.status_code == status
    media_type = response.headers["content-type"].split(";", 1)[0]
    assert media_type == "application/problem+json"
    body = response.json()
    validator.validate(body)
    assert body["status"] == status
    assert body["title"]
    assert isinstance(body["type"], str) and body["type"]
    return body
