"""Smoke: bot list → claim → enrich → propose; wrong-analyst 403."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from app.main import create_app
from app.settings import build_settings
from fastapi.testclient import TestClient
from triage_db.queue import claim_outbox

from tests.db_setup import migrate_fresh, normalize_url

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "contracts" / "examples"
WORKER_DIR = REPO / "services" / "worker"


@pytest.fixture(scope="module")
def smoke_client(migrated_test_db):
    if migrated_test_db is None:
        pytest.skip("TEST_DATABASE_URL is not set")
    raw = os.environ["TEST_DATABASE_URL"]
    url = normalize_url(raw)
    engine = migrate_fresh(url)
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


def test_bot_happy_path_and_wrong_analyst_403(
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

    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}
    listed = client.get("/v1/cases", headers=analyst_headers)
    case = listed.json()["items"][0]
    case_id = case["case_id"]
    queue = case["queue"]

    assigned = client.post(
        f"/v1/cases/{case_id}/assign",
        headers={**analyst_headers, "If-Match": str(case["version"])},
        json={"assignee": "analyst-demo"},
    )
    assert assigned.status_code == 200

    bot_headers = {"X-GrokBot-Key": bot_key}
    queue_resp = client.get("/v1/bot/queue", headers=bot_headers)
    assert queue_resp.status_code == 200
    assert any(item["case_id"] == case_id for item in queue_resp.json()["items"])

    claim = client.post(
        "/v1/bot/claim",
        headers=bot_headers,
        json={"queue": queue, "max_items": 1},
    )
    assert claim.status_code == 200
    assert claim.json()["items"][0]["case_id"] == case_id

    enrich = client.post(
        f"/v1/bot/cases/{case_id}/enrichments",
        headers=bot_headers,
        json={
            "kind": "enrichment",
            "title": "Bot: correlated VPN ASN with threat feed",
            "source": "grok-bot-demo",
            "data": {"note": "hosting ASN flagged"},
        },
    )
    assert enrich.status_code == 201
    enrich_note = "Bot: correlated VPN ASN with threat feed"

    evidence = client.get(f"/v1/cases/{case_id}/evidence", headers=analyst_headers)
    assert enrich_note in evidence.json()["summary"]

    propose = client.post(
        f"/v1/bot/cases/{case_id}/proposals",
        headers=bot_headers,
        json={
            "summary": "Recommend disable_user pending analyst review",
            "actions": [
                {
                    "type": "notify_owner",
                    "params": {"channel": "email"},
                    "rationale": "Owner should verify travel",
                    "risk": "low",
                }
            ],
        },
    )
    assert propose.status_code == 201

    other_bot = create_app(
        settings=build_settings(
            bot_keys={"other-bot-key": ("other-bot", "analyst-other")},
        )
    )
    with TestClient(other_bot) as other_client:
        denied = other_client.post(
            f"/v1/bot/cases/{case_id}/enrichments",
            headers={"X-GrokBot-Key": "other-bot-key"},
            json={
                "kind": "enrichment",
                "title": "nope",
                "source": "other",
            },
        )
    assert denied.status_code == 403