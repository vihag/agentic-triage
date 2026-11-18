"""Ingest HTTP contract: 202 accept, 200 duplicate on sid."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.main import create_app
from app.settings import build_settings
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "contracts" / "examples"
DB_DIR = REPO / "db"


@pytest.fixture(scope="module")
def ingest_client():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA public CASCADE")
        conn.exec_driver_sql("CREATE SCHEMA public")
        conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    cfg = Config(str(DB_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    os.environ["DATABASE_URL"] = url
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