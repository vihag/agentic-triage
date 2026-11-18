"""Package walk plus the ``triage_agent.rules`` entry-point group."""

from __future__ import annotations

import importlib.metadata

import pytest

from triage_agent.contract import RulePlugin
from triage_agent.loader import discover_rules, materialise
from triage_agent.rules.auth_003 import RULE as AUTH

STARTER_IDS = (
    "CROWN-001-crown-jewel-asset",
    "PRIV-002-privileged-user",
    "AUTH-003-fail-then-success-external",
    "TOR-004-tor-egress",
    "ALLOW-007-known-scanner",
    "ALLOW-011-eicar-on-ci",
)


class _Entry:
    def __init__(self, name: str, loaded: object) -> None:
        self.name = name
        self._loaded = loaded

    def load(self) -> object:
        return self._loaded


def _patch(monkeypatch: pytest.MonkeyPatch, *loaded: object) -> None:
    entries = [_Entry(f"ep-{index}", item) for index, item in enumerate(loaded)]

    def fake(**kwargs: object) -> list[_Entry]:
        assert kwargs == {"group": "triage_agent.rules"}
        return entries

    monkeypatch.setattr(importlib.metadata, "entry_points", fake)


def test_package_discovery_is_the_starter_set_in_priority_order() -> None:
    rules = discover_rules()
    assert tuple(rule.rule_id for rule in rules) == STARTER_IDS
    assert [rule.priority for rule in rules] == [10, 20, 30, 40, 70, 110]
    assert all(isinstance(rule, RulePlugin) for rule in rules)
    assert len({rule.rule_id for rule in rules}) == 6


def test_entry_point_class_is_instantiated_and_ordered(monkeypatch: pytest.MonkeyPatch) -> None:
    class Extra:
        rule_id = "EXTRA-001"
        version = "1.0.0"
        priority = 5

        def applies_to(self, alert: object) -> bool:
            return False

        def evaluate(self, alert: object, ctx: object) -> object:
            raise AssertionError("not applied")

    _patch(monkeypatch, Extra)
    rules = discover_rules()
    assert rules[0].rule_id == "EXTRA-001"
    assert len(rules) == 7
    assert type(rules[0]) is Extra


def test_same_version_from_an_entry_point_is_kept_once(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, AUTH)
    rules = discover_rules()
    assert [rule.rule_id for rule in rules].count(AUTH.rule_id) == 1
    assert next(rule for rule in rules if rule.rule_id == AUTH.rule_id) is AUTH


def test_conflicting_entry_point_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Clash:
        rule_id = AUTH.rule_id
        version = "9.9.9"
        priority = AUTH.priority

        def applies_to(self, alert: object) -> bool:
            return False

        def evaluate(self, alert: object, ctx: object) -> object:
            raise AssertionError

    _patch(monkeypatch, Clash())
    with pytest.raises(ValueError, match="duplicate rule_id"):
        discover_rules()


def test_same_version_different_priority_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Clash:
        rule_id = AUTH.rule_id
        version = AUTH.version
        priority = 99

        def applies_to(self, alert: object) -> bool:
            return False

        def evaluate(self, alert: object, ctx: object) -> object:
            raise AssertionError

    _patch(monkeypatch, Clash())
    with pytest.raises(ValueError, match="duplicate rule_id"):
        discover_rules()


@pytest.mark.parametrize(
    "loaded",
    [
        object(),
        type(
            "NoEval",
            (),
            {
                "rule_id": "X",
                "version": "1",
                "priority": 1,
                "applies_to": lambda self, alert: False,
            },
        ),
    ],
)
def test_entry_point_must_be_a_plugin(monkeypatch: pytest.MonkeyPatch, loaded: object) -> None:
    _patch(monkeypatch, loaded)
    with pytest.raises(TypeError, match="RulePlugin"):
        discover_rules()


def test_materialise_rejects_blank_identity_and_bool_priority() -> None:
    class BlankId:
        rule_id = "  "
        version = "1.0.0"
        priority = 1

        def applies_to(self, alert: object) -> bool:
            return False

        def evaluate(self, alert: object, ctx: object) -> object:
            raise AssertionError

    class BlankVersion:
        rule_id = "BLANK-001"
        version = " "
        priority = 1

        def applies_to(self, alert: object) -> bool:
            return False

        def evaluate(self, alert: object, ctx: object) -> object:
            raise AssertionError

    class BoolPriority:
        rule_id = "BOOL-001"
        version = "1.0.0"
        priority = True

        def applies_to(self, alert: object) -> bool:
            return False

        def evaluate(self, alert: object, ctx: object) -> object:
            raise AssertionError

    with pytest.raises(ValueError, match="rule_id"):
        materialise(BlankId(), source="blank-id")
    with pytest.raises(ValueError, match="version"):
        materialise(BlankVersion(), source="blank-version")
    with pytest.raises(TypeError, match="RulePlugin"):
        materialise(BoolPriority(), source="bool-priority")
