"""Load contracts/openapi.yaml and list its operations.

The served OpenAPI document is this file. FastAPI's reflective generator cannot
emit the contract's OpenAPI 3.1 external JSON Schema $refs, so app.openapi()
returns the contract and tests diff it against the file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})
ANALYST_AUTH = "analystAuth"
BOT_API_KEY = "botApiKey"
SPLUNK_TOKEN = "splunkToken"
KNOWN_SCHEMES = frozenset({ANALYST_AUTH, BOT_API_KEY, SPLUNK_TOKEN})
APPROVAL_OPERATION_IDS = frozenset({"approveAction", "rejectAction"})

_APP_DIR = Path(__file__).resolve().parent
BUNDLED_CONTRACT = _APP_DIR / "bundled_openapi.yaml"


@dataclass(frozen=True)
class Operation:
    method: str
    path: str
    operation_id: str
    tags: tuple[str, ...]
    security: tuple[tuple[str, ...], ...]


def find_contract() -> Path:
    override = os.environ.get("OPENAPI_CONTRACT_PATH")
    if override:
        path = Path(override)
        if not path.is_file():
            raise FileNotFoundError(override)
        return path
    for parent in _APP_DIR.parents:
        candidate = parent / "contracts" / "openapi.yaml"
        if candidate.is_file():
            return candidate
    if BUNDLED_CONTRACT.is_file():
        return BUNDLED_CONTRACT
    raise FileNotFoundError("contracts/openapi.yaml")


def load_contract(path: Path | None = None) -> dict[str, Any]:
    contract_path = path if path is not None else find_contract()
    loaded = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{contract_path} is not an OpenAPI document")
    return loaded


def parse_operations(spec: dict[str, Any]) -> list[Operation]:
    defined = spec.get("components", {}).get("securitySchemes", {})
    if not isinstance(defined, dict) or set(defined) != KNOWN_SCHEMES:
        raise ValueError(f"securitySchemes must be exactly {sorted(KNOWN_SCHEMES)}")
    fallback = spec.get("security", [])
    if not isinstance(fallback, list):
        raise ValueError("global security must be a list")
    operations: list[Operation] = []
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("paths must be an object")
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method, operation in item.items():
            if method not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if not isinstance(operation_id, str) or not operation_id:
                raise ValueError(f"{method.upper()} {path} is missing operationId")
            tags = operation.get("tags", [])
            if not isinstance(tags, list):
                raise ValueError(f"{operation_id} tags must be a list")
            security = _security(operation, fallback, operation_id)
            operations.append(
                Operation(
                    method=method.upper(),
                    path=str(path),
                    operation_id=operation_id,
                    tags=tuple(str(tag) for tag in tags),
                    security=security,
                )
            )
    ids = [operation.operation_id for operation in operations]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate operationId in contract")
    return operations


def _security(operation: dict[str, Any], fallback: list[Any], operation_id: str) -> tuple[tuple[str, ...], ...]:
    raw = operation["security"] if "security" in operation else fallback
    if not isinstance(raw, list):
        raise ValueError(f"{operation_id} security must be a list")
    alternatives: list[tuple[str, ...]] = []
    for requirement in raw:
        if not isinstance(requirement, dict):
            raise ValueError(f"{operation_id} security requirement must be an object")
        schemes = tuple(str(name) for name in requirement)
        for name in schemes:
            if name not in KNOWN_SCHEMES:
                raise ValueError(f"{operation_id} uses unknown security scheme {name}")
        alternatives.append(schemes)
    return tuple(alternatives)
