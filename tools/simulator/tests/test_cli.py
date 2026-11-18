"""`simulator send` posts scenario bytes to the ingest URL."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl

import pytest

from simulator.cli import main
from simulator.errors import SimulatorError
from simulator.library import SCENARIOS, resolve_scenario
from simulator.send import USER_AGENT, build_ingest_url, redact_url

TOKEN = "super-secret-token"


@dataclass
class Captured:
    path: str
    body: bytes
    content_type: str | None
    content_length: str | None
    user_agent: str | None


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - stdlib handler name
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.captured.append(
            Captured(
                path=self.path,
                body=body,
                content_type=self.headers.get("Content-Type"),
                content_length=self.headers.get("Content-Length"),
                user_agent=self.headers.get("User-Agent"),
            )
        )
        status = getattr(self.server, "response_status", 202)
        if status in {301, 302, 303, 307, 308}:
            self.send_response(status)
            self.send_header("Location", "http://127.0.0.1:1/should-not-follow")
            self.end_headers()
            return
        payload = b'{"status":"accepted"}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        return


@pytest.fixture
def ingest_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.captured = []
    server.response_status = 202
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield server, f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _query(path: str) -> dict[str, str]:
    _route, _, query = path.partition("?")
    return dict(parse_qsl(query))


def _route(path: str) -> str:
    route, _, _query = path.partition("?")
    return route


@pytest.mark.parametrize(
    ("name", "severity"),
    [
        ("credential-stuffing", "4"),
        ("escalate", "4"),
        ("eicar-on-ci", "5"),
        ("downgrade", "5"),
        ("tor-egress", "5"),
        ("unchanged-high", "5"),
        ("noisy-port-scan", "3"),
        ("unchanged-low", "3"),
        ("EICAR on CI", "5"),
    ],
)
def test_send_posts_scenario_bytes(ingest_server, capsys: pytest.CaptureFixture[str], name: str, severity: str) -> None:
    server, base = ingest_server
    canonical = resolve_scenario(name)
    expected = SCENARIOS[canonical].read_bytes()
    code = main(
        [
            "send",
            name,
            "--base-url",
            base,
            "--token",
            TOKEN,
            "--instance",
            "splunk-onprem-sg1",
        ]
    )
    captured_io = capsys.readouterr()
    assert code == 0, captured_io.err
    assert len(server.captured) == 1
    captured = server.captured[0]
    assert captured.body == expected
    assert captured.content_type == "application/json"
    assert captured.content_length == str(len(expected))
    assert captured.user_agent == USER_AGENT
    assert _route(captured.path) == "/v1/ingest/splunk/splunk-onprem-sg1"
    params = _query(captured.path)
    assert params["token"] == TOKEN
    assert params["severity"] == severity
    assert TOKEN not in captured_io.out
    assert TOKEN not in captured_io.err
    record = json.loads(captured_io.out)
    assert record["scenario"] == canonical
    assert record["status"] == 202
    assert record["dry_run"] is False
    assert record["severity"] == int(severity)
    assert "token=REDACTED" in record["url"]
    assert SCENARIOS[canonical].read_bytes() == expected


def test_severity_override_does_not_rewrite_body(ingest_server, capsys: pytest.CaptureFixture[str]) -> None:
    server, base = ingest_server
    code = main(
        [
            "send",
            "credential-stuffing",
            "--base-url",
            base,
            "--token",
            TOKEN,
            "--severity",
            "6",
        ]
    )
    assert code == 0, capsys.readouterr().err
    captured = server.captured[0]
    assert captured.body == SCENARIOS["credential-stuffing"].read_bytes()
    assert json.loads(captured.body)["result"]["severity"] == "4"
    assert _query(captured.path)["severity"] == "6"


def test_burst_posts_ten_distinct_bodies(ingest_server, capsys: pytest.CaptureFixture[str]) -> None:
    server, base = ingest_server
    code = main(["send", "burst", "--base-url", base, "--token", TOKEN])
    captured_io = capsys.readouterr()
    assert code == 0, captured_io.err
    assert len(server.captured) == 10
    assert TOKEN not in captured_io.out
    records = [json.loads(line) for line in captured_io.out.splitlines()]
    assert [record["outcome"] for record in records] == (
        ["escalate"] * 2 + ["unchanged-high"] + ["unchanged-low"] * 7
    )
    sids = []
    for captured, record in zip(server.captured, records, strict=True):
        template = SCENARIOS[record["scenario"]].read_bytes()
        old_sid = json.loads(template)["sid"]
        parsed = json.loads(captured.body)
        assert captured.body == template.replace(old_sid.encode("ascii"), parsed["sid"].encode("ascii"))
        assert _query(captured.path)["severity"] == parsed["result"]["severity"]
        sids.append(parsed["sid"])
    assert len(set(sids)) == 10


def test_duplicate_sid_http_200_is_success(ingest_server, capsys: pytest.CaptureFixture[str]) -> None:
    server, base = ingest_server
    server.response_status = 200
    code = main(["send", "credential-stuffing", "--base-url", base, "--token", TOKEN])
    assert code == 0, capsys.readouterr().err
    assert json.loads(capsys.readouterr().out)["status"] == 200


def test_http_401_fails_without_leaking_the_token(ingest_server, capsys: pytest.CaptureFixture[str]) -> None:
    server, base = ingest_server
    server.response_status = 401
    code = main(["send", "tor-egress", "--base-url", base, "--token", TOKEN])
    captured_io = capsys.readouterr()
    assert code == 1
    assert "401" in captured_io.err
    assert TOKEN not in captured_io.err
    assert TOKEN not in captured_io.out
    assert len(server.captured) == 1


def test_redirect_is_not_followed(ingest_server, capsys: pytest.CaptureFixture[str]) -> None:
    server, base = ingest_server
    server.response_status = 302
    code = main(["send", "tor-egress", "--base-url", base, "--token", TOKEN])
    captured_io = capsys.readouterr()
    assert code == 1
    assert "302" in captured_io.err
    assert len(server.captured) == 1
    assert server.captured[0].body == SCENARIOS["tor-egress"].read_bytes()


def test_burst_stops_after_the_first_http_error(ingest_server) -> None:
    server, base = ingest_server
    server.response_status = 500
    code = main(["send", "burst", "--base-url", base, "--token", TOKEN, "--timeout", "2"])
    assert code == 1
    assert len(server.captured) == 1


def test_dry_run_does_not_connect(ingest_server, capsys: pytest.CaptureFixture[str]) -> None:
    server, base = ingest_server
    code = main(["send", "noisy-port-scan", "--base-url", base, "--token", TOKEN, "--dry-run"])
    captured_io = capsys.readouterr()
    assert code == 0, captured_io.err
    assert server.captured == []
    record = json.loads(captured_io.out)
    assert record["dry_run"] is True
    assert record["status"] is None
    assert record["scenario"] == "noisy-port-scan"
    assert TOKEN not in captured_io.out


def test_dry_run_without_token_uses_a_placeholder(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["send", "noisy-port-scan", "--dry-run"])
    captured_io = capsys.readouterr()
    assert code == 0, captured_io.err
    assert "DRY-RUN" in captured_io.err
    record = json.loads(captured_io.out)
    assert record["dry_run"] is True
    assert "DRY-RUN" not in captured_io.out
    assert "token=REDACTED" in record["url"]


def test_missing_token_does_not_post(ingest_server, capsys: pytest.CaptureFixture[str]) -> None:
    server, base = ingest_server
    code = main(["send", "tor-egress", "--base-url", base])
    captured_io = capsys.readouterr()
    assert code == 2
    assert "SPLUNK_INGEST_TOKEN" in captured_io.err
    assert server.captured == []


def test_bad_instance_does_not_post(ingest_server, capsys: pytest.CaptureFixture[str]) -> None:
    server, base = ingest_server
    code = main(["send", "tor-egress", "--base-url", base, "--token", TOKEN, "--instance", "SG1"])
    assert code == 2
    assert "instance" in capsys.readouterr().err
    assert server.captured == []


def test_invalid_payload_does_not_post(
    ingest_server, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    schema = tmp_path / "reject.json"
    schema.write_text(json.dumps({"type": "object", "required": ["not-a-splunk-field"]}), encoding="utf-8")
    monkeypatch.setenv("SPLUNK_WEBHOOK_SCHEMA", str(schema))
    server, base = ingest_server
    code = main(["send", "credential-stuffing", "--base-url", base, "--token", TOKEN])
    captured_io = capsys.readouterr()
    assert code == 2
    assert "not-a-splunk-field" in captured_io.err
    assert server.captured == []


def test_connection_error(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "send",
            "tor-egress",
            "--base-url",
            "http://127.0.0.1:1",
            "--token",
            TOKEN,
            "--timeout",
            "2",
        ]
    )
    captured_io = capsys.readouterr()
    assert code == 1
    assert TOKEN not in captured_io.err
    assert "token=REDACTED" in captured_io.err


def test_unknown_scenario_on_cli(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["send", "not-a-scenario", "--token", TOKEN, "--dry-run"])
    captured_io = capsys.readouterr()
    assert code == 2
    assert "unknown scenario" in captured_io.err


def test_send_requires_a_scenario() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["send"])
    assert exc.value.code == 2


def test_list_names_every_scenario(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    for name in ("credential-stuffing", "eicar-on-ci", "tor-egress", "noisy-port-scan", "burst"):
        assert name in out
    assert "2 escalate, 1 unchanged-high, 7 unchanged-low" in out


def test_wrapper_script(simulator_root) -> None:
    script = simulator_root / "simulator"
    env = os.environ.copy()
    env["SIMULATOR_PYTHON"] = sys.executable
    proc = subprocess.run(
        [str(script), "send", "eicar-on-ci", "--dry-run", "--token", TOKEN],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert TOKEN not in proc.stdout
    record = json.loads(proc.stdout)
    assert record["scenario"] == "eicar-on-ci"
    assert record["outcome"] == "downgrade"
    assert record["severity"] == 5


def test_build_ingest_url_encodes_and_redacts() -> None:
    url = build_ingest_url("http://localhost:8080/", "sg1", "a/b c", 4)
    assert url == "http://localhost:8080/v1/ingest/splunk/sg1?token=a%2Fb+c&severity=4"
    redacted = redact_url(url)
    assert redacted == "http://localhost:8080/v1/ingest/splunk/sg1?token=REDACTED&severity=4"
    assert "a/b c" not in redacted
    with pytest.raises(SimulatorError):
        build_ingest_url("http://localhost:8080/v1", "sg1", "t", 4)
    with pytest.raises(SimulatorError):
        build_ingest_url("http://localhost:8080", "SG1", "t", 4)
    with pytest.raises(SimulatorError):
        build_ingest_url("http://localhost:8080", "sg1", "t", 0)
    with pytest.raises(SimulatorError):
        build_ingest_url("http://localhost:8080", "sg1", "", 4)
