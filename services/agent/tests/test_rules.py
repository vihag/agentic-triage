"""Behaviour and branch coverage for the six starter rules."""

from __future__ import annotations

import pytest

from triage_agent.contract import TriageContext
from triage_agent.rules.allow_007 import RULE as ALLOW_007
from triage_agent.rules.allow_011 import (
    EICAR_HASHES,
    RULE as ALLOW_011,
    is_ci_build_group,
    is_eicar,
)
from triage_agent.rules.auth_003 import (
    RULE as AUTH_003,
    is_corporate_ip,
    is_nonroutable,
    mentions_fail_then_success,
)
from triage_agent.rules.crown_001 import RULE as CROWN_001
from triage_agent.rules.priv_002 import RULE as PRIV_002
from triage_agent.rules.tor_004 import RULE as TOR_004, domain_listed, mentions_tor

CTX = TriageContext()
EICAR_SHA256 = "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f"


def _auth(
    *,
    failed: object = None,
    success: object = None,
    users: list[str] | None = None,
    src: list[str] | None = None,
    search: str = "Excessive Failed Logins Followed By Success",
    title: str = "",
    window: object = None,
    window_key: str = "window_minutes",
) -> dict:
    result: dict[str, object] = {}
    if failed is not None:
        result["failed_count"] = failed
    if success is not None:
        result["success_count"] = success
    if window is not None:
        result[window_key] = window
    entities: dict[str, list[str]] = {}
    if users is not None:
        entities["users"] = users
    if src is not None:
        entities["src_ips"] = src
    return {
        "title": title,
        "source": {"search_name": search},
        "entities": entities,
        "raw": {"result": result},
    }


class TestAuth003:
    def test_matches_example_wording(self) -> None:
        alert = _auth(failed="57", success="1", users=["jdoe"], src=["203.0.113.45"])
        result = AUTH_003.evaluate(alert, CTX)
        assert result.matched is True
        assert result.rule_version == "1.2.0"
        assert result.effect.op == "floor"
        assert result.effect.severity == "high"
        assert list(result.labels) == ["candidate:credential-stuffing"]
        assert list(result.evidence_refs) == ["ev-raw-1"]
        assert result.rationale == (
            "57 failures then 1 success for the same user "
            "from a non-corporate IP within 10 minutes."
        )

    def test_pluralisation(self) -> None:
        one = AUTH_003.evaluate(
            _auth(failed=1, success=1, users=["jdoe"], src=["203.0.113.45"]), CTX
        )
        many = AUTH_003.evaluate(
            _auth(failed=2, success=2, users=["jdoe"], src=["203.0.113.45"]), CTX
        )
        mixed = AUTH_003.evaluate(
            _auth(failed=1, success=2, users=["jdoe"], src=["203.0.113.45"]), CTX
        )
        assert one.rationale.startswith("1 failure then 1 success ")
        assert many.rationale.startswith("2 failures then 2 successes ")
        assert mixed.rationale.startswith("1 failure then 2 successes ")

    def test_reads_user_and_ip_from_raw_result(self) -> None:
        alert = {
            "source": {"search_name": "Excessive Failed Logins Followed By Success"},
            "raw": {
                "result": {
                    "user": "jdoe",
                    "src_ip": "203.0.113.45",
                    "failed_count": "3",
                    "success_count": "1",
                }
            },
        }
        assert AUTH_003.evaluate(alert, CTX).matched is True

    @pytest.mark.parametrize(
        ("failed", "success"),
        [(None, None), (None, 1), (4, None), (0, 1), (2, 0)],
    )
    def test_counts_must_both_be_positive(self, failed: object, success: object) -> None:
        alert = _auth(failed=failed, success=success, users=["jdoe"], src=["203.0.113.45"])
        result = AUTH_003.evaluate(alert, CTX)
        assert result.matched is False
        assert result.effect.op == "none"

    def test_requires_a_single_user_and_external_ip(self) -> None:
        no_user = AUTH_003.evaluate(
            _auth(failed=2, success=1, users=[], src=["203.0.113.45"]), CTX
        )
        two_users = AUTH_003.evaluate(
            _auth(failed=2, success=1, users=["a", "b"], src=["203.0.113.45"]), CTX
        )
        no_ip = AUTH_003.evaluate(_auth(failed=2, success=1, users=["jdoe"], src=[]), CTX)
        corporate = AUTH_003.evaluate(
            _auth(failed=2, success=1, users=["jdoe"], src=["10.0.0.5"]), CTX
        )
        mixed = AUTH_003.evaluate(
            _auth(failed=2, success=1, users=["jdoe"], src=["10.0.0.5", "203.0.113.45"]), CTX
        )
        assert no_user.rationale == "Fail-then-success must be for a single user."
        assert two_users.rationale == "Fail-then-success must be for a single user."
        assert no_ip.rationale == "Source IP is missing or corporate."
        assert corporate.rationale == "Source IP is missing or corporate."
        assert mixed.matched is True

    def test_window_limits(self) -> None:
        base = {"failed": 2, "success": 1, "users": ["jdoe"], "src": ["203.0.113.45"]}
        assert AUTH_003.evaluate(_auth(**base, window=0), CTX).matched is False
        over = AUTH_003.evaluate(_auth(**base, window=11), CTX)
        assert "outside the 10 minute limit" in over.rationale
        assert AUTH_003.evaluate(_auth(**base, window=10), CTX).matched is True
        assert AUTH_003.evaluate(_auth(**base, window=5), CTX).matched is True
        quiet = _auth(
            failed=2,
            success=1,
            users=["jdoe"],
            src=["203.0.113.45"],
            search="Port scan",
            title="scan",
        )
        assert AUTH_003.evaluate(quiet, CTX).rationale == "No 10 minute window on this alert."

    def test_applies_to(self) -> None:
        assert mentions_fail_then_success({"title": "port scan"}) is False
        assert mentions_fail_then_success({"title": "failed login"}) is False
        assert mentions_fail_then_success({"title": "Failed then Success"}) is True
        assert AUTH_003.applies_to({"source": {"search_name": "port scan"}}) is False
        assert AUTH_003.applies_to(_auth(search="port scan", failed=1, success=1)) is True
        assert AUTH_003.applies_to(_auth(search="port scan", failed=1)) is False
        assert AUTH_003.applies_to(_auth()) is True

    def test_corporate_classification(self) -> None:
        assert is_nonroutable("not-an-ip") is False
        assert is_nonroutable("127.0.0.1") is True
        assert is_nonroutable("169.254.1.1") is True
        assert is_nonroutable("::1") is True
        assert is_nonroutable("fe80::1") is True
        assert is_nonroutable("fc00::1") is True
        assert is_nonroutable("2001:db8::1") is False
        assert is_nonroutable("10.1.2.3") is True
        assert is_nonroutable("172.16.0.1") is True
        assert is_nonroutable("192.168.1.1") is True
        assert is_nonroutable("203.0.113.45") is False
        assert is_nonroutable("8.8.8.8") is False
        assert is_corporate_ip("10.0.0.1", CTX) is True
        assert is_corporate_ip("8.8.8.8", CTX) is False
        listed = TriageContext(allow_lists={"corporate_ips": ["8.8.8.8"]})
        assert is_corporate_ip("8.8.8.8", listed) is True
        assert is_corporate_ip("203.0.113.45", listed) is False
        assert is_corporate_ip("10.0.0.1", listed) is True
        cidr = TriageContext(allow_lists={"corporate_cidrs": ["203.0.113.0/24"]})
        alert = _auth(failed=2, success=1, users=["jdoe"], src=["203.0.113.45"])
        assert AUTH_003.evaluate(alert, cidr).matched is False


class TestAllow007:
    def test_unmatched_wording(self) -> None:
        result = ALLOW_007.evaluate({"entities": {"src_ips": ["203.0.113.45"]}}, CTX)
        assert result.matched is False
        assert result.effect.op == "none"
        assert result.rationale == "Source IP not in scanner allow-list."

    def test_exact_and_later_ip_and_cidr(self) -> None:
        exact = TriageContext(allow_lists={"scanners": ["203.0.113.45"]})
        later = TriageContext(allow_lists={"known_scanners": ["10.1.1.1"]})
        cidr = TriageContext(allow_lists={"scanner_ips": ["10.8.0.0/16"]})
        exact_result = ALLOW_007.evaluate({"entities": {"src_ips": ["203.0.113.45"]}}, exact)
        later_result = ALLOW_007.evaluate(
            {"entities": {"src_ips": ["203.0.113.45", "10.1.1.1"]}}, later
        )
        cidr_result = ALLOW_007.evaluate({"raw": {"result": {"src_ip": "10.8.1.4"}}}, cidr)
        assert exact_result.matched is True
        assert exact_result.effect == later_result.effect
        assert exact_result.effect.op == "ceiling"
        assert exact_result.effect.severity == "low"
        assert list(exact_result.labels) == ["benign:known-scanner"]
        assert later_result.rationale == "Source IP 10.1.1.1 is in the scanner allow-list."
        assert cidr_result.matched is True

    def test_no_source_ip(self) -> None:
        assert ALLOW_007.applies_to({}) is False
        assert ALLOW_007.applies_to({"entities": {"src_ips": ["10.0.0.1"]}}) is True
        result = ALLOW_007.evaluate({}, CTX)
        assert result.rationale == "Alert has no source IP to check against the scanner allow-list."


class TestAllow011:
    def test_group_and_hash_detection(self) -> None:
        assert is_ci_build_group(None) is False
        assert is_ci_build_group("   ") is False
        assert is_ci_build_group("production") is False
        assert is_ci_build_group("ci-build") is True
        assert is_ci_build_group("build-agents") is True
        assert is_ci_build_group("CI Build Agents") is True
        assert is_ci_build_group("ci_build_agents") is True
        assert is_eicar({"entities": {"file_hashes": [EICAR_SHA256.upper()]}}) is True
        md5 = "44d88612fea8a8f36de82e1278abb02f"
        sha1 = "3395856ce81f2b7382dee72602f798b642f14140"
        assert is_eicar({"entities": {"file_hashes": [md5]}}) is True
        assert is_eicar({"entities": {"file_hashes": [sha1]}}) is True
        assert is_eicar({"entities": {"file_hashes": ["abc", EICAR_SHA256]}}) is True
        assert is_eicar({"entities": {"file_hashes": ["abc"]}}) is False
        assert is_eicar({"raw": {"result": {"signature": "EICAR-Test-File"}}}) is True
        assert is_eicar({"title": "EICAR on workstation"}) is True
        assert is_eicar({"description": "dropped eicar.com"}) is True
        trojan = {"title": "trojan", "raw": {"result": {"signature": "Trojan.Generic"}}}
        assert is_eicar(trojan) is False
        assert EICAR_SHA256 in EICAR_HASHES

    def test_match_and_each_miss(self) -> None:
        ci = TriageContext(asset_inventory={"build-agent-07": {"group": "ci-build-agents"}})
        eicar = {"entities": {"hosts": ["build-agent-07"], "file_hashes": [EICAR_SHA256]}}
        matched = ALLOW_011.evaluate(eicar, ci)
        assert matched.matched is True
        assert matched.effect.op == "ceiling"
        assert matched.effect.severity == "low"
        assert list(matched.labels) == ["benign:av-selftest"]
        assert list(matched.evidence_refs) == ["ev-raw-1"]
        assert matched.rationale == "EICAR test hash on a host in the CI build-agent asset group."
        assert "CI build-agent" in ALLOW_011.evaluate(eicar, CTX).rationale
        other = {"entities": {"hosts": ["build-agent-07"], "file_hashes": ["abc"]}}
        assert ALLOW_011.evaluate(other, ci).rationale.startswith("Host is in the CI build-agent")
        neither = {"entities": {"hosts": ["laptop"], "file_hashes": ["abc"]}}
        assert ALLOW_011.evaluate(neither, ci).rationale == (
            "Not an EICAR test hash on a CI build-agent."
        )

    def test_case_insensitive_host_and_applies_to(self) -> None:
        ctx = TriageContext(asset_inventory={"Build-Agent-07": {"group": "build-agent"}})
        alert = {"entities": {"hosts": ["build-agent-07"], "file_hashes": [EICAR_SHA256]}}
        assert ALLOW_011.evaluate(alert, ctx).matched is True
        assert ALLOW_011.applies_to({"entities": {"file_hashes": ["abc"]}}) is True
        assert ALLOW_011.applies_to({"raw": {"result": {"signature": "EICAR"}}}) is True
        malware = {"source": {"search_name": "Malware Signature Detected"}}
        assert ALLOW_011.applies_to(malware) is True
        assert ALLOW_011.applies_to({"title": "EICAR test"}) is True
        assert ALLOW_011.applies_to({"title": "port scan"}) is False


class TestCrown001:
    def test_single_host_wording(self) -> None:
        alert = {"entities": {"hosts": ["build-agent-07"]}}
        missed = CROWN_001.evaluate(alert, CTX)
        assert missed.matched is False
        assert missed.rationale == "build-agent-07 is not a crown-jewel asset."
        jewel = TriageContext(asset_inventory={"build-agent-07": {"crown_jewel": True}})
        hit = CROWN_001.evaluate(alert, jewel)
        assert hit.matched is True
        assert hit.effect.op == "never_auto_close"
        assert hit.effect.severity is None
        assert hit.rationale == "build-agent-07 is a crown-jewel asset."
        assert list(hit.labels) == ["guard:crown-jewel"]

    def test_flags_and_multiple_hosts(self) -> None:
        yes = TriageContext(asset_inventory={"DB-01": {"crown_jewel": "yes"}})
        assert CROWN_001.evaluate({"raw": {"result": {"host": "db-01"}}}, yes).matched is True
        zero = TriageContext(asset_inventory={"h": {"crown_jewel": 0}})
        assert CROWN_001.evaluate({"entities": {"hosts": ["h"]}}, zero).matched is False
        both = TriageContext(
            asset_inventory={"a": {"crown_jewel": True}, "b": {"crown_jewel": "true"}}
        )
        plural = CROWN_001.evaluate({"entities": {"hosts": ["a", "b"]}}, both)
        assert plural.rationale == "a, b are crown-jewel assets."
        one = TriageContext(asset_inventory={"a": {"crown_jewel": 1}})
        assert CROWN_001.evaluate({"entities": {"hosts": ["a", "b"]}}, one).rationale == (
            "a is a crown-jewel asset."
        )
        none = CROWN_001.evaluate({"entities": {"hosts": ["a", "b"]}}, CTX)
        assert none.rationale == "a, b are not crown-jewel assets."

    def test_applies_to_and_empty(self) -> None:
        assert CROWN_001.applies_to({}) is False
        assert CROWN_001.applies_to({"entities": {"hosts": ["h"]}}) is True
        assert CROWN_001.evaluate({}, CTX).rationale.startswith("Alert has no host")


class TestPriv002:
    def test_plus_one_for_one_or_many(self) -> None:
        ctx = TriageContext(identity_directory={"root": {"privileged": True, "dept": "it"}})
        one = PRIV_002.evaluate({"entities": {"users": ["root"]}}, ctx)
        assert one.matched is True
        assert one.effect.op == "delta"
        assert one.effect.delta == 1
        assert one.effect.severity is None
        assert one.rationale == "User root is privileged (+1 severity)."
        assert list(one.labels) == ["guard:privileged-user"]
        many_ctx = TriageContext(
            identity_directory={"root": {"privileged": "true"}, "ops": {"privileged": "yes"}}
        )
        many = PRIV_002.evaluate({"entities": {"users": ["root", "ops"]}}, many_ctx)
        assert many.effect.delta == 1
        assert many.rationale == "Users root, ops are privileged (+1 severity)."
        partial = PRIV_002.evaluate({"entities": {"users": ["root", "jdoe"]}}, ctx)
        assert partial.rationale == "User root is privileged (+1 severity)."

    def test_not_privileged(self) -> None:
        assert PRIV_002.evaluate({"entities": {"users": ["jdoe"]}}, CTX).rationale == (
            "User jdoe is not privileged."
        )
        both = PRIV_002.evaluate({"entities": {"users": ["a", "b"]}}, CTX)
        assert both.rationale == "Users a, b are not privileged."
        folded = TriageContext(identity_directory={"Alice": {"privileged": False}})
        assert PRIV_002.evaluate({"raw": {"result": {"user": "alice"}}}, folded).matched is False

    def test_applies_to_and_empty(self) -> None:
        assert PRIV_002.applies_to({}) is False
        assert PRIV_002.applies_to({"entities": {"users": ["jdoe"]}}) is True
        assert PRIV_002.evaluate({}, CTX).rationale.startswith("Alert has no user")


class TestTor004:
    def test_domain_list(self) -> None:
        assert domain_listed("  ", ["tor.example"]) is False
        assert domain_listed("exit.tor.example", ["", "10.0.0.0/8", "tor.example"]) is True
        assert domain_listed("tor.example", ["tor.example"]) is True
        assert domain_listed("nottor.example", ["tor.example"]) is False
        assert domain_listed("exit.tor.example.", ["TOR.example"]) is True

    def test_ip_domain_and_text(self) -> None:
        exits = TriageContext(
            allow_lists={"tor_exit_nodes": ["185.220.101.1", "exit.tor.example"]}
        )
        by_ip = TOR_004.evaluate(
            {"title": "TOR egress", "entities": {"dest_ips": ["8.8.8.8", "185.220.101.1"]}},
            exits,
        )
        assert by_ip.matched is True
        assert by_ip.effect.op == "floor"
        assert by_ip.effect.severity == "high"
        assert by_ip.rationale == "Destination 185.220.101.1 is a TOR exit node."
        assert list(by_ip.labels) == ["candidate:tor-egress"]
        assert list(by_ip.evidence_refs) == ["ev-raw-1"]
        by_domain = TOR_004.evaluate({"entities": {"domains": ["exit.tor.example"]}}, exits)
        assert by_domain.rationale == "Destination exit.tor.example is a TOR exit node."
        by_text = TOR_004.evaluate({"title": "Outbound TOR egress"}, CTX)
        assert by_text.rationale == "Alert indicates TOR egress."
        other_list = TriageContext(allow_lists={"tor_exits": ["1.1.1.1"]})
        assert TOR_004.evaluate({"entities": {"dest_ips": ["1.1.1.1"]}}, other_list).matched is True

    def test_non_match_and_word_boundaries(self) -> None:
        missed = TOR_004.evaluate({"entities": {"dest_ips": ["8.8.8.8"]}}, CTX)
        assert missed.matched is False
        assert missed.rationale == "Destination is not a known TOR exit node."
        assert mentions_tor({"title": "TOR egress"}) is True
        assert mentions_tor({"description": "seen on tor."}) is True
        assert mentions_tor({"title": "monitoring tornado history"}) is False
        assert mentions_tor({"raw": {"result": {"signature": "TORexit"}}}) is False
        assert TOR_004.applies_to({"entities": {"dest_ips": ["8.8.8.8"]}}) is True
        assert TOR_004.applies_to({"entities": {"domains": ["example.com"]}}) is True
        assert TOR_004.applies_to({"title": "TOR egress"}) is True
        assert TOR_004.applies_to({"title": "port scan"}) is False
