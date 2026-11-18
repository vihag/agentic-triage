"""Validate a re-read document against the JSON Schema its example file names."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMAS = Path(__file__).resolve().parents[2] / "contracts" / "schemas"


@cache
def _registry() -> tuple[Registry, dict[str, dict]]:
    schemas: dict[str, dict] = {}
    registry: Registry = Registry()
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        contents = json.loads(path.read_text())
        schemas[path.name] = contents
        resource = Resource.from_contents(contents, default_specification=DRAFT202012)
        registry = registry.with_resource(path.name, resource).with_resource(path.as_uri(), resource)
    return registry, schemas


def assert_matches_example_schema(example_name: str, document: object) -> None:
    registry, schemas = _registry()
    schema_file = f"{example_name.split('.', 1)[0]}.schema.json"
    if schema_file not in schemas:
        raise AssertionError(f"no schema {schema_file} for {example_name}")
    validator = Draft202012Validator(schemas[schema_file], registry=registry, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda err: list(err.path))
    assert not errors, errors[0].message
