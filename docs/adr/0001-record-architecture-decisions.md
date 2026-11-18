# ADR-0001: Record architecture decisions

* Status: Accepted · Date: 2026-11-18 · Owner: Architect

## Context
Seven roles (many of them coding agents) work in parallel for four days. Decisions must be findable and not re-litigated.

## Decision
Lightweight ADRs (Context / Decision / Consequences) in `docs/adr/`, numbered, immutable once accepted (supersede, don't edit). Any PR touching `contracts/` with behavioural impact links an ADR.

## Consequences
Agents get decisions as plain files they can read before coding. Small overhead per decision.
