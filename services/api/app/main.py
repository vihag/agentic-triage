"""Triage API.

Every operation in the loaded OpenAPI contract is mounted. healthz is live.
Everything else returns 501 after the contract's auth scheme succeeds. The
document served at /openapi.json is the contract file, not FastAPI's
reflective schema, so the two diff clean.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.audit import AuditHook, LoggingAuditHook
from app.problems import install_exception_handlers
from app.routing import register_routes
from app.settings import Settings, load_settings
from app.spec import load_contract, parse_operations


class ContractApp(FastAPI):
    """FastAPI app whose generated OpenAPI document is the contract."""

    def __init__(self, spec: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._contract_spec = spec

    def openapi(self) -> dict[str, Any]:
        return copy.deepcopy(self._contract_spec)


def create_app(
    settings: Settings | None = None,
    audit: AuditHook | None = None,
    contract_path: Path | None = None,
) -> ContractApp:
    spec = load_contract(contract_path)
    operations = parse_operations(spec)
    info = spec.get("info", {})
    app = ContractApp(
        spec,
        title=str(info.get("title", "Agentic Triage API")),
        version=str(info.get("version", "0.1.0")),
        summary=info.get("summary") if isinstance(info.get("summary"), str) else None,
        description=info.get("description") if isinstance(info.get("description"), str) else None,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.settings = settings if settings is not None else load_settings()
    app.state.audit = audit if audit is not None else LoggingAuditHook()
    install_exception_handlers(app)
    register_routes(app, operations)
    return app


app = create_app()
