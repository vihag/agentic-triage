# ADR-0007: Contract-first development

* Status: Accepted · Date: 2026-11-18 · Owner: Architect

## Decision
`contracts/` (OpenAPI 3.1, JSON Schema 2020-12, agent Protocols, examples) is written and validated **before** implementation and is the single source of truth. Every example must validate; negative examples must fail; the OpenAPI must lint clean (`scripts/validate_contracts.py`, CI-blocking). Code is generated from or tested against the contracts (Pydantic models via datamodel-code-generator, TS types via openapi-typescript, Schemathesis, Pact). Contract changes are separate PRs owned per `docs/team.md`.

## Consequences
Parallel work from day one, modular tests, mocks for free. Contract changes cost a little more ceremony, on purpose.
