from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
import yaml
from app.audit import AuthDeniedNotice
from app.auth import mint_analyst_token
from app.main import create_app
from app.settings import Settings, build_settings
from app.spec import Operation, parse_operations
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from tests.helpers import CONTRACT_PATH

DEFAULT_BOT_KEY = "local-dev-grok-bot-key"
DEFAULT_SPLUNK_TOKEN = "local-dev-splunk-webhook-token"


class RecordingAudit:
    def __init__(self) -> None:
        self.events: list[AuthDeniedNotice] = []

    def record_auth_denied(self, notice: AuthDeniedNotice) -> None:
        self.events.append(notice)


@pytest.fixture
def contract() -> dict:
    loaded = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture
def operations(contract: dict) -> list[Operation]:
    return parse_operations(contract)


@pytest.fixture
def problem_validator(contract: dict) -> Draft202012Validator:
    return Draft202012Validator(contract["components"]["schemas"]["Problem"])


@pytest.fixture
def audit() -> RecordingAudit:
    return RecordingAudit()


@pytest.fixture
def settings() -> Settings:
    return build_settings()


@pytest.fixture
def client(settings: Settings, audit: RecordingAudit) -> Iterator[TestClient]:
    if test_url := os.environ.get("TEST_DATABASE_URL"):
        os.environ["DATABASE_URL"] = test_url
    elif not os.environ.get("DATABASE_URL"):
        os.environ["DATABASE_URL"] = "postgresql+psycopg://127.0.0.1:9/triage_test"
    application = create_app(settings=settings, audit=audit)
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture
def analyst_token(settings: Settings) -> str:
    return mint_analyst_token(settings, "analyst-demo", display_name="Demo Analyst")


@pytest.fixture
def bot_key() -> str:
    return DEFAULT_BOT_KEY


@pytest.fixture
def splunk_token() -> str:
    return DEFAULT_SPLUNK_TOKEN
