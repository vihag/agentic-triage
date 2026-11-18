"""Scenario bytes, burst recipe, and schema validation of every payload."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simulator.errors import SimulatorError
from simulator.library import (
    BURST_RECIPE,
    BURST_SIZE,
    SCENARIOS,
    iter_messages,
    resolve_scenario,
)
from simulator.validate import find_schema, load_validator, validate_messages


def _fixed_sid(index: int, scenario: str) -> str:
    slug = scenario.replace("-", "_")
    return f"scheduler__admin__simulator__{slug}_{index:02d}"


def _result_values_are_splunk_strings(result: object) -> None:
    assert isinstance(result, dict)
    for key, value in result.items():
        if isinstance(value, str):
            continue
        assert isinstance(value, list), key
        assert value, key
        assert all(isinstance(item, str) for item in value), key


@pytest.mark.parametrize("name", [*SCENARIOS, "burst"])
def test_every_generated_payload_validates_against_schema(name: str, schema_path: Path) -> None:
    messages = iter_messages(name, sid_factory=_fixed_sid)
    validate_messages(messages, schema_path)
    for message in messages:
        payload = json.loads(message.body)
        assert payload["sid"] == message.sid
        assert payload["search_name"]
        _result_values_are_splunk_strings(payload["result"])


def test_contract_invalid_example_is_rejected(schema_path: Path, repo_root: Path) -> None:
    raw = json.loads(
        (repo_root / "contracts" / "examples" / "invalid" / "splunk-webhook.missing-sid.json").read_text(
            encoding="utf-8"
        )
    )
    errors = list(load_validator(schema_path).iter_errors(raw))
    assert errors


def test_numeric_severity_is_rejected(schema_path: Path) -> None:
    payload = json.loads(SCENARIOS["credential-stuffing"].read_bytes())
    payload["result"]["severity"] = 4
    errors = list(load_validator(schema_path).iter_errors(payload))
    assert errors


def test_empty_sid_is_rejected(schema_path: Path) -> None:
    payload = json.loads(SCENARIOS["tor-egress"].read_bytes())
    payload["sid"] = ""
    errors = list(load_validator(schema_path).iter_errors(payload))
    assert errors


def test_catalog_files_match_package(simulator_root: Path) -> None:
    directory = simulator_root / "src" / "simulator" / "scenarios"
    on_disk = {path.name for path in directory.glob("*.json")}
    catalog = {scenario.filename for scenario in SCENARIOS.values()}
    assert on_disk == catalog
    for scenario in SCENARIOS.values():
        assert scenario.read_bytes() == (directory / scenario.filename).read_bytes()


def test_contract_backed_scenarios_match_examples(repo_root: Path) -> None:
    matched = 0
    for scenario in SCENARIOS.values():
        if scenario.contract_example is None:
            continue
        expected = (repo_root / "contracts" / "examples" / scenario.contract_example).read_bytes()
        assert scenario.read_bytes() == expected
        matched += 1
    assert matched == 2


def test_named_scenarios_keep_file_bytes() -> None:
    for name, scenario in SCENARIOS.items():
        (message,) = iter_messages(name)
        assert message.body == scenario.read_bytes()
        assert message.body.endswith(b"\n")
        assert not message.body.endswith(b"\n\n")
        assert message.outcome == scenario.outcome


def test_scenario_identity() -> None:
    assert SCENARIOS["credential-stuffing"].outcome == "escalate"
    assert SCENARIOS["eicar-on-ci"].outcome == "downgrade"
    assert SCENARIOS["tor-egress"].outcome == "unchanged-high"
    assert SCENARIOS["noisy-port-scan"].outcome == "unchanged-low"

    stuffing = json.loads(SCENARIOS["credential-stuffing"].read_bytes())
    eicar = json.loads(SCENARIOS["eicar-on-ci"].read_bytes())
    tor = json.loads(SCENARIOS["tor-egress"].read_bytes())
    scan = json.loads(SCENARIOS["noisy-port-scan"].read_bytes())
    assert stuffing["search_name"] == "Excessive Failed Logins Followed By Success"
    assert stuffing["result"]["severity"] == "4"
    assert eicar["search_name"] == "Malware Signature Detected On Endpoint"
    assert eicar["result"]["signature"] == "EICAR-Test-File"
    assert eicar["result"]["severity"] == "5"
    assert tor["search_name"] == "Outbound Connection To TOR Exit Node"
    assert tor["result"]["severity"] == "5"
    assert tor["result"]["category"] == "tor-exit"
    assert scan["search_name"] == "Noisy External Port Scan"
    assert scan["result"]["severity"] == "3"
    assert scan["result"]["dest_port"] == ["22", "80", "443", "3389", "8080"]


def test_burst_recipe_matches_testing_doc() -> None:
    assert BURST_SIZE == 10
    assert BURST_RECIPE == (
        ("credential-stuffing", 2),
        ("tor-egress", 1),
        ("noisy-port-scan", 7),
    )
    messages = iter_messages("burst", sid_factory=_fixed_sid)
    assert [message.scenario for message in messages] == (
        ["credential-stuffing"] * 2 + ["tor-egress"] + ["noisy-port-scan"] * 7
    )
    assert [message.outcome for message in messages].count("escalate") == 2
    assert [message.outcome for message in messages].count("unchanged-high") == 1
    assert [message.outcome for message in messages].count("unchanged-low") == 7
    assert len({message.sid for message in messages}) == 10


def test_burst_replaces_only_the_sid_text() -> None:
    messages = iter_messages("burst", sid_factory=_fixed_sid)
    for message in messages:
        template = SCENARIOS[message.scenario].read_bytes()
        old_sid = json.loads(template)["sid"]
        assert message.body == template.replace(old_sid.encode("ascii"), message.sid.encode("ascii"))
        parsed = json.loads(message.body)
        assert parsed["results_link"].endswith(message.sid)
        assert old_sid not in message.body.decode("ascii")


def test_burst_rejects_duplicate_or_unsafe_sids() -> None:
    with pytest.raises(SimulatorError, match="duplicate sids"):
        iter_messages("burst", sid_factory=lambda _index, _scenario: "scheduler__admin__simulator__same")
    with pytest.raises(SimulatorError, match="Splunk-safe"):
        iter_messages("burst", sid_factory=lambda _index, _scenario: 'bad"sid')


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [
        ("escalate", "credential-stuffing"),
        ("credential stuffing", "credential-stuffing"),
        ("EICAR on CI", "eicar-on-ci"),
        ("downgrade", "eicar-on-ci"),
        ("unchanged-high", "tor-egress"),
        ("TOR egress", "tor-egress"),
        ("unchanged-low", "noisy-port-scan"),
        ("noisy port scan", "noisy-port-scan"),
        ("burst mode", "burst"),
        ("Burst", "burst"),
    ],
)
def test_resolve_aliases(alias: str, canonical: str) -> None:
    assert resolve_scenario(alias) == canonical


def test_unknown_scenario() -> None:
    with pytest.raises(SimulatorError, match="unknown scenario"):
        resolve_scenario("not-a-scenario")


def test_find_schema_is_the_contract(schema_path: Path) -> None:
    assert find_schema() == schema_path
    assert schema_path.name == "splunk-webhook.schema.json"


def test_missing_schema_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPLUNK_WEBHOOK_SCHEMA", str(tmp_path / "missing.json"))
    with pytest.raises(SimulatorError, match="SPLUNK_WEBHOOK_SCHEMA"):
        find_schema()
