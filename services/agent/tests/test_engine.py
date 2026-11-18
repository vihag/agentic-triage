"""Rule engine: priority order, and a recorded result for every plugin."""

from __future__ import annotations

import pytest

from triage_agent.contract import RuleResult, SeverityEffect, TriageContext
from triage_agent.engine import RuleEngine
from triage_agent.results import unmatched


class Spy:
    def __init__(
        self,
        rule_id: str = "SPY-001",
        version: str = "1.0.0",
        priority: int = 1,
        *,
        applies: bool = True,
        result: object = None,
        boom: str | None = None,
    ) -> None:
        self.rule_id = rule_id
        self.version = version
        self.priority = priority
        self.applies = applies
        self.result = result
        self.boom = boom
        self.calls = 0

    def applies_to(self, alert: object) -> bool:
        if self.boom == "applies":
            raise RuntimeError("applies")
        return self.applies

    def evaluate(self, alert: object, ctx: object) -> object:
        self.calls += 1
        if self.boom == "eval":
            raise RuntimeError("eval")
        if self.result is not None:
            return self.result
        return unmatched(self.rule_id, self.version, "spy")


def test_explicit_rules_sort_by_priority_then_id_and_ignore_discovery() -> None:
    later = Spy("B-002", priority=5)
    early = Spy("C-003", priority=1)
    tie = Spy("A-001", priority=1)
    engine = RuleEngine([later, early, tie])
    assert [rule.rule_id for rule in engine.rules] == ["A-001", "C-003", "B-002"]


def test_duplicate_rule_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate rule_id"):
        RuleEngine([Spy("SAME"), Spy("SAME", priority=2)])


def test_non_rule_is_rejected() -> None:
    with pytest.raises(TypeError, match="RulePlugin"):
        RuleEngine([object()])  # type: ignore[list-item]


def test_not_applicable_is_recorded_without_calling_evaluate() -> None:
    spy = Spy(applies=False)
    result = RuleEngine([spy]).run({})
    assert spy.calls == 0
    assert result[0].matched is False
    assert result[0].effect.op == "none"
    assert result[0].rationale == "SPY-001 does not apply to this alert."


def test_evaluate_result_is_kept_when_identity_matches() -> None:
    produced = unmatched("SPY-001", "1.0.0", "because")
    spy = Spy(result=produced)
    assert RuleEngine([spy]).run({}, None)[0] is produced
    assert spy.calls == 1


def test_engine_stamps_plugin_identity_over_a_mismatched_result() -> None:
    spy = Spy(result=RuleResult("OTHER", "9.9.9", True, SeverityEffect("floor", "high"), "why"))
    stamped = RuleEngine([spy]).run({})[0]
    assert stamped.rule_id == "SPY-001"
    assert stamped.rule_version == "1.0.0"
    assert stamped.matched is True
    assert stamped.effect.op == "floor"
    assert stamped.rationale == "why"

    version_only = Spy(
        result=RuleResult("SPY-001", "9.9.9", False, SeverityEffect("none"), "no"),
    )
    stamped_version = RuleEngine([version_only]).run({})[0]
    assert stamped_version.rule_version == "1.0.0"
    assert stamped_version.rationale == "no"


def test_evaluate_must_return_a_rule_result() -> None:
    spy = Spy(result="nope")
    with pytest.raises(TypeError, match="RuleResult"):
        RuleEngine([spy]).run({})


def test_exceptions_propagate() -> None:
    with pytest.raises(RuntimeError, match="eval"):
        RuleEngine([Spy(boom="eval")]).run({})
    with pytest.raises(RuntimeError, match="applies"):
        RuleEngine([Spy(boom="applies")]).run({})


def test_input_types() -> None:
    engine = RuleEngine([Spy(applies=False)])
    with pytest.raises(TypeError, match="mapping"):
        engine.run(["not", "a", "mapping"])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="TriageContext"):
        engine.run({}, object())  # type: ignore[arg-type]
    assert engine.run({}, TriageContext())[0].rule_id == "SPY-001"
