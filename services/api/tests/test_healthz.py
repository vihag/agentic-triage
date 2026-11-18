from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_healthz_ok() -> None:
    response = client.get("/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unauthenticated_ingest_is_rejected() -> None:
    response = client.post("/v1/ingest/splunk/sg1")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
