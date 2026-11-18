"""Schemathesis against behavior this ticket implements.

501 stubs are excluded. A full-spec run would fail status and server-error
checks on those responses, and that behavior belongs to later tickets.

These runs use Schemathesis' default checks on:

- GET /v1/healthz
- POST /v1/ingest/splunk/{instance} (generated tokens are not the webhook secret)
- approve and reject with a real bot key, which must be 403

approve/reject omit the missing-Authorization coverage check. That check
hardcodes 401, while a present bot key is specified to be 403 and the contract
does not document 401 on those operations.
"""

from __future__ import annotations

from pathlib import Path

import schemathesis
from app.main import create_app
from app.settings import build_settings
from schemathesis.config import SchemathesisConfig
from schemathesis.specs.openapi.checks import missing_required_header

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "openapi.yaml"
BOT_KEY = "schemathesis-bot-key-do-not-guess-9f3c2a7b1e"
SPLUNK_TOKEN = "schemathesis-splunk-token-do-not-guess-c4e81d0a"

APP = create_app(
    settings=build_settings(
        jwt_secret="schemathesis-jwt-secret-do-not-guess-88ab44",
        splunk_webhook_token=SPLUNK_TOKEN,
        bot_keys={BOT_KEY: ("schemathesis-bot", "schemathesis-analyst")},
    )
)

SCHEMA = schemathesis.openapi.from_path(CONTRACT, config=SchemathesisConfig(seed=20261118))
SCHEMA.app = APP
SCHEMA.config.phases.fuzzing.generation.update(max_examples=12)
SCHEMA.config.phases.examples.generation.update(max_examples=8)
SCHEMA.config.phases.stateful.enabled = False


@SCHEMA.include(operation_id="healthz").parametrize()
def test_schemathesis_healthz(case) -> None:
    case.call_and_validate()


@SCHEMA.include(operation_id="ingestSplunkAlert").parametrize()
def test_schemathesis_ingest_rejects_unknown_token(case) -> None:
    response = case.call_and_validate()
    assert response.status_code != 202
    assert response.status_code < 500


@SCHEMA.include(operation_id=["approveAction", "rejectAction"]).parametrize()
def test_schemathesis_bot_cannot_approve_or_reject(case) -> None:
    response = case.call_and_validate(
        headers={"X-GrokBot-Key": BOT_KEY},
        excluded_checks=[missing_required_header],
    )
    # Coverage also sends methods the contract does not declare; those are 405.
    if response.request.method.upper() == "POST":
        assert response.status_code == 403
    else:
        assert response.status_code == 405
