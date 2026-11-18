"""Branch coverage for the pure alert accessors."""

from __future__ import annotations

from triage_agent.contract import TriageContext
from triage_agent.rules.fields import (
    allow_values,
    as_int,
    description_text,
    dest_ips_of,
    domains_of,
    failure_success_counts,
    file_hashes_of,
    flag_is_true,
    host_record,
    hosts_of,
    identity_record,
    ip_in_list,
    lookup_record,
    raw_result,
    search_name,
    signature_of,
    src_ips_of,
    strings,
    title_text,
    users_of,
    window_minutes,
)


def test_strings_shapes() -> None:
    assert strings(" jdoe ") == ["jdoe"]
    assert strings("   ") == []
    assert strings(b"abc") == []
    assert strings(bytearray(b"abc")) == []
    assert strings(None) == []
    assert strings({"user": "jdoe"}) == []
    assert strings([" jdoe ", "", "  ", 3, None]) == ["jdoe"]


def test_text_and_raw_fallbacks() -> None:
    assert search_name({"source": {"search_name": "Excessive Failed Logins"}}) == (
        "Excessive Failed Logins"
    )
    assert search_name({"source": {"search_name": 4}}) == ""
    assert search_name({}) == ""
    assert title_text({"title": "TOR egress"}) == "TOR egress"
    assert title_text({"title": 1}) == ""
    assert description_text({"description": "notes"}) == "notes"
    assert description_text({"description": None}) == ""
    assert raw_result({"raw": {"result": {"user": "jdoe"}}}) == {"user": "jdoe"}
    assert raw_result({"raw": "webhook"}) == {}
    assert raw_result({"raw": {"result": ["nope"]}}) == {}
    assert raw_result({}) == {}


def test_entity_prefers_entities_then_raw() -> None:
    alert = {
        "entities": {"users": ["from-entity"], "src_ips": ["10.0.0.1"]},
        "raw": {"result": {"user": "from-raw", "src_ip": "10.9.9.9", "dest_ip": "8.8.8.8"}},
    }
    assert users_of(alert) == ["from-entity"]
    assert src_ips_of(alert) == ["10.0.0.1"]
    raw_only = {"raw": {"result": {"user": "jdoe", "src_ip": "203.0.113.45", "host": "vpn"}}}
    assert users_of(raw_only) == ["jdoe"]
    assert src_ips_of(raw_only) == ["203.0.113.45"]
    assert hosts_of(raw_only) == ["vpn"]
    assert users_of({}) == []
    assert src_ips_of({"entities": "nope"}) == []
    second_key = {"raw": {"result": {"src_ips": ["198.51.100.10"]}}}
    assert src_ips_of(second_key) == ["198.51.100.10"]
    assert dest_ips_of({"entities": {"dest_ips": ["1.1.1.1"]}}) == ["1.1.1.1"]
    assert dest_ips_of({"raw": {"result": {"dest_ip": "9.9.9.9"}}}) == ["9.9.9.9"]
    assert domains_of({"entities": {"domains": ["exit.example"]}}) == ["exit.example"]
    assert domains_of({"raw": {"result": {"domain": "tor.example"}}}) == ["tor.example"]
    assert hosts_of({"entities": {"hosts": ["h1"]}}) == ["h1"]
    assert file_hashes_of({"entities": {"file_hashes": ["ABC"]}}) == ["abc"]
    assert file_hashes_of({"raw": {"result": {"file_hash": "DEF"}}}) == ["def"]


def test_signature_joins_present_text_fields() -> None:
    alert = {"raw": {"result": {"signature": " EICAR ", "signature_id": "  ", "threat_name": 3}}}
    assert signature_of(alert) == "EICAR"
    both = {"raw": {"result": {"signature": "EICAR", "threat_name": "test"}}}
    assert signature_of(both) == "EICAR test"
    assert signature_of({}) == ""


def test_as_int_and_windows() -> None:
    assert as_int(True) is None
    assert as_int(False) is None
    assert as_int(None) is None
    assert as_int(57) == 57
    assert as_int(0) == 0
    assert as_int(2.0) == 2
    assert as_int(2.5) is None
    assert as_int(" 57 ") == 57
    assert as_int("  ") is None
    assert as_int("nope") is None
    assert as_int(["57"]) is None
    counts = failure_success_counts(
        {"raw": {"result": {"failed_count": "57", "success_count": 1}}}
    )
    assert counts == (57, 1)
    assert window_minutes({"raw": {"result": {"window_minutes": "10"}}}) == 10
    assert window_minutes({"raw": {"result": {"window_min": 5}}}) == 5
    assert window_minutes({"raw": {"result": {"window_minutes": "x", "window_min": 5}}}) is None
    assert window_minutes({}) is None


def test_allow_values_and_lookups() -> None:
    ctx = TriageContext(
        allow_lists={"scanners": ["10.0.0.8"], "scanner_ips": ["10.1.1.1"], "empty": []},
        asset_inventory={
            "Host-A": {"crown_jewel": True},
            "skip": "not-a-record",
            "Other": {"group": "prod"},
        },
        identity_directory={"Alice": {"privileged": True}, "bob": "nope"},
    )
    assert allow_values(ctx, "missing", "scanners", "scanner_ips") == ["10.0.0.8", "10.1.1.1"]
    assert host_record(ctx, "Host-A") == {"crown_jewel": True}
    assert host_record(ctx, "host-a") == {"crown_jewel": True}
    assert host_record(ctx, "skip") == {}
    assert host_record(ctx, "missing") == {}
    assert identity_record(ctx, "alice") == {"privileged": True}
    assert identity_record(ctx, "bob") == {}
    assert lookup_record({"plain": "x", "Plain-Rec": {"ok": 1}}, "plain-rec") == {"ok": 1}


def test_flag_is_true() -> None:
    assert flag_is_true(True) is True
    assert flag_is_true(False) is False
    assert flag_is_true(2) is True
    assert flag_is_true(0) is False
    assert flag_is_true(" yes ") is True
    assert flag_is_true("TRUE") is True
    assert flag_is_true("1") is True
    assert flag_is_true("y") is True
    assert flag_is_true("false") is False
    assert flag_is_true(["true"]) is False


def test_ip_in_list() -> None:
    assert ip_in_list("10.0.0.5", ["10.0.0.5"])
    assert ip_in_list("10.8.1.4", ["10.8.0.0/16"])
    assert not ip_in_list("11.0.0.1", ["10.0.0.0/8"])
    assert ip_in_list("not-an-ip", ["not-an-ip"])
    assert not ip_in_list("not-an-ip", ["10.0.0.0/8"])
    assert not ip_in_list("not-an-ip", ["other"])
    assert not ip_in_list("10.0.0.1", ["10.0.0.2"])
    assert not ip_in_list("10.0.0.1", ["nope/24"])
    assert not ip_in_list("10.0.0.1", [])
    assert not ip_in_list("10.0.0.1", ["fe80::/10"])
