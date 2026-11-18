"""Smoke: ingest → worker → list case → approve; bot approve returns 403."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.main import create_app
from app.settings import build_settings
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from triage_db.queue import claim_outbox

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "contracts" / "examples"
DB_DIR = REPO / "db"
WORKER_DIR = REPO / "services" / "worker"


def _normalize_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    return url


def _migrate(url: str) -> None:
    os.environ["DATABASE_URL"] = url
    cfg = Config(str(DB_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(DB_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


@pytest.fixture(scope="module")
def smoke_client():
    raw = os.environ.get("TEST_DATABASE_URL")
    if not raw:
        pytest.skip("TEST_DATABASE_URL is not set")
    url = _normalize_url(raw)
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP SCHEMA public CASCADE")
        conn.exec_driver_sql("CREATE SCHEMA public")
        conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
    _migrate(url)
    application = create_app(settings=build_settings())
    with TestClient(application) as client:
        yield client, engine
    engine.dispose()


def _run_worker_once(engine) -> None:
    sys.path.insert(0, str(WORKER_DIR))
    from worker import process_claim  # noqa: WPS433

    with engine.begin() as conn:
        claimed = claim_outbox(conn, max_items=1, lease_seconds=60)
        for row in claimed:
            process_claim(conn, row.id, row.alert_id)


def test_console_slice_happy_path_and_bot_403(
    smoke_client: tuple[TestClient, object],
    splunk_token: str,
    analyst_token: str,
    bot_key: str,
) -> None:
    client, engine = smoke_client
    body = json.loads((EXAMPLES / "splunk-webhook.escalate.json").read_text())
    ingest = client.post(
        "/v1/ingest/splunk/splunk-onprem-sg1",
        params={"token": splunk_token},
        json=body,
    )
    assert ingest.status_code == 202
    _run_worker_once(engine)

    headers = {"Authorization": f"Bearer {analyst_token}"}
    listed = client.get("/v1/cases", headers=headers)
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) >= 1
    case_id = items[0]["case_id"]

    detail = client.get(f"/v1/cases/{case_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.headers.get("etag")

    evidence = client.get(f"/v1/cases/{case_id}/evidence", headers=headers)
    assert evidence.status_code == 200
    assert evidence.json().get("summary")

    steps = client.get(f"/v1/cases/{case_id}/next-steps", headers=headers)
    assert steps.status_code == 200

    actions = client.get(f"/v1/cases/{case_id}/actions", headers=headers)
    assert actions.status_code == 200
    proposed = [a for a in actions.json() if a["status"] == "proposed"]
    assert proposed, "worker should leave proposed actions"
    action_id = proposed[0]["action_id"]

    approved = client.post(
        f"/v1/cases/{case_id}/actions/{action_id}/approve",
        headers=headers,
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "executed"

    bot_headers = {"Authorization": f"Bearer {analyst_token}", "X-GrokBot-Key": bot_key}
    pending = client.get(f"/v1/cases/{case_id}/actions", headers=headers).json()
    still_proposed = [a for a in pending if a["status"] == "proposed"]
    if not still_proposed:
        created = client.post(
            f"/v1/cases/{case_id}/actions",
            headers=headers,
            json={
                "type": "notify_owner",
                "params": {"channel": "email"},
                "rationale": "smoke test propose",
                "risk": "low",
            },
        )
        assert created.status_code == 201
        other_id = created.json()["action_id"]
    else:
        other_id = still_proposed[0]["action_id"]

    denied = client.post(
        f"/v1/cases/{case_id}/actions/{other_id}/approve",
        headers=bot_headers,
    )
    assert denied.status_code == 403