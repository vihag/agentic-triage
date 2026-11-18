"""Discover ``RulePlugin`` implementations from a package and entry points.

The contract names both sources: the ``triage_agent.rules`` package and the
``triage_agent.rules`` entry-point group. A module contributes a plugin by
exporting ``RULE``. Entry points may load that same object or a class with a
zero-argument constructor.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import pkgutil
from typing import cast

from triage_agent.contract import RulePlugin


def _looks_like_rule(obj: object) -> bool:
    applies = getattr(obj, "applies_to", None)
    evaluate = getattr(obj, "evaluate", None)
    if not callable(applies) or not callable(evaluate):
        return False
    if not isinstance(getattr(obj, "rule_id", None), str):
        return False
    if not isinstance(getattr(obj, "version", None), str):
        return False
    return type(getattr(obj, "priority", None)) is int


def validate_rule(rule: RulePlugin) -> None:
    if rule.rule_id.strip() == "":
        raise ValueError("rule_id must be a non-empty string")
    if rule.version.strip() == "":
        raise ValueError(f"{rule.rule_id}: version must be a non-empty string")
    if type(rule.priority) is not int:
        raise TypeError(f"{rule.rule_id}: priority must be an int")


def materialise(loaded: object, *, source: str) -> RulePlugin:
    candidate = loaded() if isinstance(loaded, type) else loaded
    if not _looks_like_rule(candidate):
        raise TypeError(f"{source} did not produce a RulePlugin")
    rule = cast(RulePlugin, candidate)
    validate_rule(rule)
    return rule


def _add(found: dict[str, RulePlugin], rule: RulePlugin) -> None:
    current = found.get(rule.rule_id)
    if current is None:
        found[rule.rule_id] = rule
        return
    if current.version != rule.version or current.priority != rule.priority:
        raise ValueError(
            f"duplicate rule_id {rule.rule_id!r} "
            f"({current.version} p{current.priority} vs {rule.version} p{rule.priority})"
        )


def _package_rules(package_name: str) -> list[RulePlugin]:
    package = importlib.import_module(package_name)
    rules: list[RulePlugin] = []
    prefix = package_name + "."
    for info in pkgutil.iter_modules(package.__path__, prefix):
        module = importlib.import_module(info.name)
        if not hasattr(module, "RULE"):
            continue
        rules.append(materialise(module.RULE, source=info.name))
    return rules


def _entry_point_rules(group: str) -> list[RulePlugin]:
    rules: list[RulePlugin] = []
    for entry in importlib.metadata.entry_points(group=group):
        rules.append(materialise(entry.load(), source=f"entry point {entry.name}"))
    return rules


def discover_rules(package_name: str = "triage_agent.rules") -> list[RulePlugin]:
    """Return plugins from ``package_name`` and the matching entry-point group.

    The same id and version contributed by both sources is kept once. A second
    contribution with a different version or priority is an error.
    """
    found: dict[str, RulePlugin] = {}
    for rule in _package_rules(package_name):
        _add(found, rule)
    for rule in _entry_point_rules(package_name):
        _add(found, rule)
    return sorted(found.values(), key=lambda rule: (rule.priority, rule.rule_id))
