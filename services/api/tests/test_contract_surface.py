from __future__ import annotations

from app.main import app, create_app
from app.spec import BUNDLED_CONTRACT, parse_operations
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from tests.helpers import CONTRACT_PATH, assert_problem

# Present after contract PR #33. Auth is enforced here; the bodies are T16.
STUBBED_BOT_READS = frozenset({"botGetCaseBundle", "listBotRuns"})


def test_served_openapi_matches_contract(contract: dict) -> None:
    application = create_app()
    assert application.openapi() == contract
    with TestClient(application) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json() == contract


def test_routes_match_contract_operations(contract: dict) -> None:
    application = create_app()
    expected = {
        (operation.method, operation.path, operation.operation_id) for operation in parse_operations(contract)
    }
    actual: set[tuple[str, str, str]] = set()
    for route in application.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/v1/"):
            methods = set(route.methods or ()) - {"HEAD"}
            operation_id = route.operation_id
            assert operation_id is not None
            for method in methods:
                actual.add((method, route.path, operation_id))
    assert actual == expected
    operation_ids = {operation_id for _, _, operation_id in actual}
    assert STUBBED_BOT_READS <= operation_ids


def test_bundled_contract_matches_source() -> None:
    assert BUNDLED_CONTRACT.read_bytes() == CONTRACT_PATH.read_bytes()


def test_healthz_schema_and_no_auth(client: TestClient, contract: dict) -> None:
    response = client.get("/v1/healthz", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    schema = contract["paths"]["/v1/healthz"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    Draft202012Validator(schema).validate(response.json())
    assert response.json() == {"status": "ok"}


def test_uvicorn_app_healthz() -> None:
    with TestClient(app) as client:
        response = client.get("/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_path_and_method_are_problem_json(client: TestClient, problem_validator) -> None:
    missing = client.get("/v1/does-not-exist")
    body = assert_problem(missing, problem_validator, 404)
    assert body["instance"] == "/v1/does-not-exist"

    method = client.post("/v1/healthz")
    assert_problem(method, problem_validator, 405)
    assert "GET" in method.headers["allow"]
