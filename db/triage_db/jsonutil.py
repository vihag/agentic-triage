"""JSON helpers for jsonb columns.

Postgres jsonb does not preserve object key order. Callers compare parsed
documents, which is the round-trip the JSON Schemas describe.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def load_json(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


def parse_ts(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
