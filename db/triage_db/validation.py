"""Validate an AuditEvent against contracts/schemas/audit-event.schema.json."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMAS = Path(__file__).resolve().parents[2] / "contracts" / "schemas"


@cache
def _audit_validator() -> Draft202012Validator:
    registry: Registry = Registry()
    schemas: dict[str, dict[str, Any]] = {}
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        contents = json.loads(path.read_text())
        schemas[path.name] = contents
        resource = Resource.from_contents(contents, default_specification=DRAFT202012)
        registry = registry.with_resource(path.name, resource).with_resource(path.as_uri(), resource)
    return Draft202012Validator(
        schemas["audit-event.schema.json"],
        registry=registry,
        format_checker=FormatChecker(),
    )


def validate_audit_event(event: dict[str, Any]) -> None:
    errors = sorted(_audit_validator().iter_errors(event), key=lambda err: list(err.absolute_path))
    if errors:
        raise ValueError(errors[0].message)
