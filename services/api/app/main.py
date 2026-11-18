"""Triage API scaffold.

The only route is GET /v1/healthz. T06 replaces this module with the operations
in contracts/openapi.yaml. Docs and the generated OpenAPI route are off so this
process does not publish a spec that could drift from the contract.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(
    title="Agentic Triage API",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/v1/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
