from __future__ import annotations

import base64
import json
import time

import jwt
import pytest
from app.auth import ApprovalResult, HmacJwtVerifier, approval_guard, mint_analyst_token
from app.main import create_app
from app.principals import AnalystPrincipal, BotPrincipal
from app.problems import validation_problem
from app.settings import build_settings
from app.spec import ANALYST_AUTH, APPROVAL_OPERATION_IDS, BOT_API_KEY, SPLUNK_TOKEN
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from jwt import InvalidTokenError

from tests.conftest import RecordingAudit
from tests.helpers import ACTION_ID, CASE_ID, assert_problem, fill_path

APPROVE = f"/v1/cases/{CASE_ID}/actions/{ACTION_ID}/approve"
REJECT = f"/v1/cases/{CASE_ID}/actions/{ACTION_ID}/reject"
_BACKEND_READS = frozenset({"getAlert", "getTriageDecision"})
_IMPLEMENTED_SLICE = frozenset(
    {
        "listCases",
        "getCase",
        "getEvidencePack",
        "getNextStepsPack",
        "claimNext",
        "releaseCase",
        "assignCase",
        "transitionCase",
        "listActions",
        "proposeAction",
        "approveAction",
        "rejectAction",
    }
)


def _segment(value: dict) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=")
    return raw.decode("ascii")


def _unsigned(payload: dict) -> str:
    return _segment({"alg": "none", "typ": "JWT"}) + "." + _segment(payload) + "."


def test_approval_guard_rejects_bot_even_with_analyst() -> None:
    bot = BotPrincipal(id="bot-a", on_behalf_of="analyst-a")
    analyst = AnalystPrincipal(id="analyst-a")
    assert approval_guard(bot, analyst) is ApprovalResult.DENY_BOT
    assert approval_guard(bot, None) is ApprovalResult.DENY_BOT
    assert approval_guard(None, None) is ApprovalResult.UNAUTHENTICATED
    assert approval_guard(None, analyst) is ApprovalResult.ALLOW


def test_bot_key_maps_to_bot_id_and_analyst() -> None:
    settings = build_settings(bot_keys={"key-a": ("bot-a", "analyst-a"), "key-b": ("bot-b", "analyst-b")})
    first = settings.bot_keys.resolve("key-a")
    second = settings.bot_keys.resolve("key-b")
    assert first is not None and first.bot_id == "bot-a" and first.on_behalf_of == "analyst-a"
    assert second is not None and second.bot_id == "bot-b" and second.on_behalf_of == "analyst-b"
    assert settings.bot_keys.resolve("nope") is None
    assert settings.bot_keys.resolve("key-a-extra") is None


def test_hmac_verifier_rejects_bad_tokens(settings) -> None:
    verifier = HmacJwtVerifier(settings)
    now = int(time.time())
    good = jwt.encode(
        {"sub": "analyst-1", "iss": settings.jwt_issuer, "aud": settings.jwt_audience, "iat": now, "exp": now + 60},
        settings.jwt_secret,
        algorithm="HS256",
    )
    assert isinstance(good, str)
    principal = verifier.verify(good)
    assert principal is not None and principal.id == "analyst-1"

    expired = jwt.encode(
        {"sub": "analyst-1", "iss": settings.jwt_issuer, "aud": settings.jwt_audience, "iat": now - 120, "exp": now - 60},
        settings.jwt_secret,
        algorithm="HS256",
    )
    assert isinstance(expired, str)
    assert verifier.verify(expired) is None

    other = jwt.encode(
        {"sub": "analyst-1", "iss": settings.jwt_issuer, "aud": settings.jwt_audience, "exp": now + 60},
        "different-secret",
        algorithm="HS256",
    )
    assert isinstance(other, str)
    assert verifier.verify(other) is None

    wrong_audience = jwt.encode(
        {"sub": "analyst-1", "iss": settings.jwt_issuer, "aud": "some-other-api", "exp": now + 60},
        settings.jwt_secret,
        algorithm="HS256",
    )
    assert isinstance(wrong_audience, str)
    assert verifier.verify(wrong_audience) is None

    unsigned = _unsigned(
        {"sub": "analyst-1", "iss": settings.jwt_issuer, "aud": settings.jwt_audience, "exp": now + 60}
    )
    assert verifier.verify(unsigned) is None
    with pytest.raises(InvalidTokenError):
        jwt.decode(unsigned, settings.jwt_secret, algorithms=["HS256"])


def test_every_operation_enforces_its_scheme(
    client: TestClient,
    operations,
    problem_validator,
    analyst_token: str,
    bot_key: str,
    splunk_token: str,
) -> None:
    seen: set[str] = set()
    bearer = {"Authorization": f"Bearer {analyst_token}"}
    for operation in operations:
        seen.add(operation.operation_id)
        url = fill_path(operation.path)
        if not operation.security:
            response = client.request(operation.method, url, headers={"Authorization": "Bearer nope"})
            assert response.status_code == 200, operation.operation_id
            continue

        missing = client.request(operation.method, url)
        body = assert_problem(missing, problem_validator, 401)
        assert body["instance"] == url

        scheme = operation.security[0][0]
        if scheme == ANALYST_AUTH:
            if operation.operation_id in APPROVAL_OPERATION_IDS:
                denied = client.request(operation.method, url, headers={"X-GrokBot-Key": bot_key})
                assert_problem(denied, problem_validator, 403)
            else:
                wrong_scheme = client.request(operation.method, url, headers={"X-GrokBot-Key": bot_key})
                assert_problem(wrong_scheme, problem_validator, 401)
            accepted = client.request(operation.method, url, headers=bearer)
            if operation.operation_id in _BACKEND_READS | _IMPLEMENTED_SLICE:
                assert accepted.status_code in (200, 201, 204, 404, 409, 412, 422, 500)
            else:
                assert_problem(accepted, problem_validator, 501)
        elif scheme == BOT_API_KEY:
            accepted = client.request(operation.method, url, headers={"X-GrokBot-Key": bot_key})
            assert_problem(accepted, problem_validator, 501)
            analyst = client.request(operation.method, url, headers=bearer)
            assert_problem(analyst, problem_validator, 401)
            bad_key = client.request(operation.method, url, headers={"X-GrokBot-Key": "not-a-real-key"})
            assert_problem(bad_key, problem_validator, 401)
        elif scheme == SPLUNK_TOKEN:
            accepted = client.request(operation.method, url, params={"token": splunk_token})
            if operation.operation_id == "ingestSplunkAlert":
                assert accepted.status_code in (422, 500)
            else:
                assert_problem(accepted, problem_validator, 501)
            wrong = client.request(operation.method, url, params={"token": "wrong-token"})
            problem = assert_problem(wrong, problem_validator, 401)
            assert "wrong-token" not in wrong.text
            assert problem["instance"] == url
            missing_token = client.request(operation.method, url, headers=bearer)
            assert_problem(missing_token, problem_validator, 401)
        else:
            raise AssertionError(scheme)

    assert APPROVAL_OPERATION_IDS <= seen
    assert "botGetCaseBundle" in seen
    assert "listBotRuns" in seen


def test_bot_cannot_approve_or_reject_and_denial_is_hooked(problem_validator, audit: RecordingAudit) -> None:
    settings = build_settings(bot_keys={"key-a": ("bot-a", "analyst-a")})
    token = mint_analyst_token(settings, "analyst-demo")
    application = create_app(settings=settings, audit=audit)
    with TestClient(application) as local:
        for path, _operation_id in ((APPROVE, "approveAction"), (REJECT, "rejectAction")):
            denied = local.post(
                path,
                headers={
                    "X-GrokBot-Key": "key-a",
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                content=b"{",
            )
            body = assert_problem(denied, problem_validator, 403)
            assert body["detail"] == "Bot credentials cannot approve or reject actions."

            lowercase = local.post(path, headers={"x-grokbot-key": "key-a"})
            assert_problem(lowercase, problem_validator, 403)

        assert len(audit.events) == 4
        for event in audit.events:
            assert event.event_type == "auth.denied"
            assert event.actor.type == "grok_bot"
            assert event.actor.id == "bot-a"
            assert event.actor.on_behalf_of == "analyst-a"
            assert event.case_id == CASE_ID
            assert event.action_id == ACTION_ID
            assert event.operation_id in {"approveAction", "rejectAction"}

        audit.events.clear()
        invalid_key = local.post(APPROVE, headers={"X-GrokBot-Key": "nope", "Authorization": f"Bearer {token}"})
        assert invalid_key.status_code in (404, 500)
        assert audit.events == []

        unauthenticated = local.post(APPROVE)
        assert_problem(unauthenticated, problem_validator, 401)
        assert audit.events == []


def test_bot_bundle_and_run_list_are_auth_then_501(
    client: TestClient,
    problem_validator,
    analyst_token: str,
    bot_key: str,
    audit: RecordingAudit,
) -> None:
    """T16 owns the bundle and the run list. This ticket only authenticates."""

    bundle = f"/v1/bot/cases/{CASE_ID}/bundle"
    missing_bundle = client.get(bundle)
    assert_problem(missing_bundle, problem_validator, 401)
    bundled = client.get(bundle, headers={"X-GrokBot-Key": bot_key})
    assert_problem(bundled, problem_validator, 501)
    analyst_on_bundle = client.get(bundle, headers={"Authorization": f"Bearer {analyst_token}"})
    assert_problem(analyst_on_bundle, problem_validator, 401)

    missing_runs = client.get("/v1/bot-runs")
    assert_problem(missing_runs, problem_validator, 401)
    bot_on_runs = client.get("/v1/bot-runs", headers={"X-GrokBot-Key": bot_key})
    assert_problem(bot_on_runs, problem_validator, 401)
    listed = client.get("/v1/bot-runs", headers={"Authorization": f"Bearer {analyst_token}"})
    assert_problem(listed, problem_validator, 501)
    assert audit.events == []


def test_validation_errors_are_problem_json() -> None:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": "/v1/ingest/splunk/splunk-prod",
        "raw_path": b"/v1/ingest/splunk/splunk-prod",
        "query_string": b"",
        "headers": [],
        "scheme": "http",
        "server": ("test", 80),
        "client": ("test", 5000),
    }
    request = Request(scope)
    exc = RequestValidationError(
        [{"loc": ("body", "sid"), "msg": "Field required", "type": "missing", "input": "sekret"}]
    )
    response = validation_problem(request, exc)
    assert response.status_code == 422
    assert response.media_type == "application/problem+json"
    raw = bytes(response.body)
    body = json.loads(raw)
    assert body["status"] == 422
    assert "sekret" not in raw.decode()
    assert "sid" in body["detail"]
