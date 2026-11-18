"""Validate matcher output against FuzzyMatchResult in the frozen schema."""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from typing import Any, cast

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from triage_agent.contract import repo_root


def _load(name: str) -> dict[str, Any]:
    path = repo_root() / "contracts" / "schemas" / name
    loaded: dict[str, Any] = json.loads(path.read_text())
    return loaded


@lru_cache(maxsize=1)
def fuzzy_match_schema() -> dict[str, Any]:
    """Self-contained copy of ``#/$defs/FuzzyMatchResult`` for the LLM call."""
    decision = _load("triage-decision.schema.json")
    common = _load("common.schema.json")
    severity = common["$defs"]["Severity"]
    confidence = common["$defs"]["Confidence"]
    similar = copy.deepcopy(decision["$defs"]["SimilarItem"])
    similar["properties"]["verified_severity"] = severity
    fuzzy = copy.deepcopy(decision["$defs"]["FuzzyMatchResult"])
    fuzzy["title"] = "FuzzyMatchResult"
    fuzzy["properties"]["suggested_severity"] = severity
    fuzzy["properties"]["confidence"] = confidence
    fuzzy["properties"]["similar_items"]["items"] = similar
    return cast(dict[str, Any], fuzzy)


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    registry: Registry = Registry()
    root = repo_root() / "contracts" / "schemas"
    for path in sorted(root.glob("*.schema.json")):
        contents = json.loads(path.read_text())
        resource = Resource.from_contents(contents, default_specification=DRAFT202012)
        registry = registry.with_resource(path.name, resource)
    return Draft202012Validator(
        {"$ref": "triage-decision.schema.json#/$defs/FuzzyMatchResult"},
        registry=registry,
    )


def validate_fuzzy_match(payload: dict[str, Any]) -> None:
    """Raise ``ValueError`` when ``payload`` is not a FuzzyMatchResult."""
    errors = sorted(_validator().iter_errors(payload), key=lambda err: list(err.path))
    if errors:
        first = errors[0]
        where = "/".join(str(part) for part in first.path)
        location = f"{where}: " if where else ""
        raise ValueError(f"FuzzyMatchResult invalid: {location}{first.message}")
