# ADR-0002: Python + FastAPI for the API; triage agent as an in-process library

* Status: Accepted · Date: 2026-11-18 · Owner: Architect

## Context
We need an HTTP API with strict request/response validation, and an agent that combines deterministic rules with ML/LLM calls. The ML ecosystem (embeddings, pgvector clients, LLM SDKs) is strongest in Python.

## Decision
* Backend: **Python 3.12 + FastAPI + Pydantic v2**, SQLAlchemy 2 / psycopg 3, Alembic.
* Triage agent: a **Python library** (`services/agent`) called by the worker, behind the Protocols in `contracts/agent/interfaces.py`, not a separate network service in v1.
* FastAPI's generated OpenAPI is diffed against `contracts/openapi.yaml` in CI (the contract wins).

## Alternatives
* Go/Java API: faster, but splits the stack in two languages for a 4-day build.
* Agent as its own microservice: cleaner scaling, but adds a network contract and failure mode; we can extract it later because the Protocol boundary already exists.

## Consequences
One language for API, worker, agent and simulator. Worker scales horizontally; if LLM latency dominates we extract the agent behind the same interface.
