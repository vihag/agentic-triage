"""Validate webhook bodies against the frozen Splunk webhook schema."""

from __future__ import annotations

import json
import os
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from simulator.errors import SimulatorError
from simulator.library import WebhookMessage

_SCHEMA_NAME = "splunk-webhook.schema.json"


def find_schema() -> Path:
    """Locate ``contracts/schemas/splunk-webhook.schema.json``.

    ``SPLUNK_WEBHOOK_SCHEMA`` wins. Otherwise walk parents of this file, which
    finds the schema when the simulator runs from a checkout of the repo.
    """
    override = os.environ.get("SPLUNK_WEBHOOK_SCHEMA")
    if override:
        path = Path(override)
        if not path.is_file():
            raise SimulatorError(f"SPLUNK_WEBHOOK_SCHEMA is not a file: {path}")
        return path
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "contracts" / "schemas" / _SCHEMA_NAME
        if candidate.is_file():
            return candidate
    raise SimulatorError(
        "Cannot find contracts/schemas/splunk-webhook.schema.json. "
        "Run from a checkout of the repo, or set SPLUNK_WEBHOOK_SCHEMA."
    )


def load_validator(schema_path: Path) -> Draft202012Validator:
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SimulatorError(f"cannot read webhook schema {schema_path}: {exc}") from exc
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_messages(messages: tuple[WebhookMessage, ...] | list[WebhookMessage], schema_path: Path) -> None:
    """Raise ``SimulatorError`` if any body fails the Splunk webhook schema."""
    validator = load_validator(schema_path)
    problems: list[str] = []
    for message in messages:
        try:
            instance = json.loads(message.body)
        except json.JSONDecodeError as exc:
            problems.append(f"{message.scenario} sid={message.sid}: invalid JSON ({exc})")
            continue
        errors = sorted(validator.iter_errors(instance), key=lambda err: list(err.absolute_path))
        for err in errors:
            location = ".".join(str(part) for part in err.absolute_path) or "<root>"
            problems.append(f"{message.scenario} sid={message.sid} {location}: {err.message}")
    if problems:
        detail = "\n".join(problems)
        raise SimulatorError(f"payload failed {_SCHEMA_NAME}:\n{detail}")
