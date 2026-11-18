"""Hypothesis: every rule is total and records a contract-shaped result."""

from __future__ import annotations

from hypothesis import example, given, settings, strategies as st

from triage_agent.contract import TriageContext
from triage_agent.engine import RuleEngine

ENGINE = RuleEngine()
NAMES = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122),
    min_size=1,
    max_size=8,
)
IPS = st.sampled_from(["10.0.0.5", "203.0.113.45", "8.8.8.8", "192.168.1.9", "not-an-ip"])
EICAR = "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f"

ALERTS = st.fixed_dictionaries(
    {},
    optional={
        "title": st.text(max_size=40),
        "description": st.text(max_size=40),
        "source": st.fixed_dictionaries({"search_name": st.text(max_size=60)}),
        "entities": st.fixed_dictionaries(
            {},
            optional={
                "users": st.lists(NAMES, max_size=3),
                "src_ips": st.lists(IPS, max_size=2),
                "dest_ips": st.lists(IPS, max_size=2),
                "hosts": st.lists(NAMES, max_size=2),
                "domains": st.lists(
                    st.sampled_from(["example.com", "exit.tor.example", "nottor.example"]),
                    max_size=2,
                ),
                "file_hashes": st.lists(st.sampled_from(["abc", EICAR]), max_size=2),
            },
        ),
        "raw": st.fixed_dictionaries(
            {
                "result": st.fixed_dictionaries(
                    {},
                    optional={
                        "failed_count": st.integers(min_value=-1, max_value=6),
                        "success_count": st.integers(min_value=-1, max_value=3),
                        "window_minutes": st.integers(min_value=-1, max_value=20),
                        "signature": st.sampled_from(["EICAR-Test-File", "Trojan", ""]),
                        "user": NAMES,
                        "src_ip": IPS,
                        "host": NAMES,
                    },
                )
            }
        ),
    },
)

_RECORD = st.fixed_dictionaries(
    {},
    optional={
        "crown_jewel": st.one_of(st.booleans(), st.sampled_from(["true", "false", "yes"])),
        "group": st.sampled_from(["ci-build-agents", "production", "build-agent", ""]),
        "privileged": st.one_of(st.booleans(), st.sampled_from(["true", "false"])),
    },
)

CONTEXTS = st.builds(
    TriageContext,
    asset_inventory=st.dictionaries(NAMES, _RECORD, max_size=2),
    identity_directory=st.dictionaries(NAMES, _RECORD, max_size=2),
    allow_lists=st.fixed_dictionaries(
        {
            "scanners": st.lists(IPS, max_size=2),
            "corporate_ips": st.lists(IPS, max_size=1),
            "tor_exit_nodes": st.lists(
                st.sampled_from(["185.220.101.1", "exit.tor.example", "10.0.0.0/8"]),
                max_size=2,
            ),
        }
    ),
    now_iso=st.just(""),
)


@settings(max_examples=40, derandomize=True, deadline=None)
@given(alert=ALERTS, ctx=CONTEXTS)
@example(alert={}, ctx=TriageContext())
def test_rules_are_total_and_record_every_result(alert: dict, ctx: TriageContext) -> None:
    results = ENGINE.run(alert, ctx)
    assert [result.rule_id for result in results] == [rule.rule_id for rule in ENGINE.rules]
    for result, rule in zip(results, ENGINE.rules, strict=True):
        assert result.rule_version == rule.version
        assert result.rationale
        assert -2 <= result.effect.delta <= 2
        if result.matched:
            assert result.effect.op != "none"
        else:
            assert result.effect.op == "none"
            assert result.effect.delta == 0
            assert result.effect.severity is None
            assert list(result.labels) == []
            assert list(result.evidence_refs) == []
        if result.effect.op == "delta":
            assert result.rule_id == "PRIV-002-privileged-user"
            assert result.effect.delta == 1
        elif result.effect.op != "delta":
            assert result.effect.delta == 0
