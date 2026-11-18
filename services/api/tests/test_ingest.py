"""Ingest HTTP contract: 202 accept, 200 duplicate on sid."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from app.main import create_app
from app.settings import build_settings
from fastapi.testclient import TestClient

from tests.db_setup import migrate_fresh, normalize_url

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "contracts" / "examples"


@pytest.fixture(scope="module")
def ingest_client(migrated_test_db):
    if migrated_test_db is None:
        pytest.skip("TEST_DATABASE_URL is not set")
    raw = os.environ["TEST_DATABASE_URL"]
    url = normalize_url(raw)
    engine = migrate_fresh(url)
    application = create_app(settings=build_settings())
    with TestClient(application) as client:
        yield client
    engine.dispose()


def _webhook(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text())


def test_ingest_accepts_and_dedups(ingest_client: TestClient, splunk_token: str) -> None:
    body = _webhook("splunk-webhook.escalate.json")
    url = "/v1/ingest/splunk/splunk-onprem-sg1"
    first = ingest_client.post(url, params={"token": splunk_token}, json=body)
    assert first.status_code == 202
    payload = first.json()
    assert payload["status"] == "accepted"
    alert_id = payload["alert_id"]

    second = ingest_client.post(url, params={"token": splunk_token}, json=body)
    assert second.status_code == 200
    duplicate = second.json()
    assert duplicate["status"] == "duplicate"
    assert duplicate["alert_id"] == alert_id