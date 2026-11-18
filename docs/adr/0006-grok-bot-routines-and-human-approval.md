# ADR-0006: Grok Bot routines act on behalf of analysts; humans approve every action

* Status: Accepted · Date: 2026-11-18 · Owner: Architect

## Context
We want each SOC analyst "10x-ed": a Grok Bot routine picks up the newest items in the analyst's queue, enriches them, drafts responses and proposes actions, so the analyst spends time deciding, not gathering.

## Decision
* **Identity:** each analyst gets a bot API key (`X-GrokBot-Key`) bound to `{bot_id, on_behalf_of: analyst_id}`. Every bot write is audited as `actor={type: grok_bot, id, on_behalf_of}`.
* **Scope:** bot endpoints (`/v1/bot/*`) only see and claim cases whose `assignee` is that analyst.
* **Capabilities:** bots may *read*, *claim*, *append enrichment evidence* (read-only lookups, e.g. Splunk drill-down searches, directory, threat intel) and *propose* actions and drafts. Bots **cannot approve, reject, execute, or close**.
* **Enforcement in three layers:** (1) OpenAPI: `approve`/`reject` declare `analystAuth` only, and the contract gate lints this; (2) API: approval guard rejects non-analyst principals with 403 + `auth.denied` audit; (3) schema: `action.schema.json` requires `decided_by.type == analyst` for any decided status (an invalid example proves it). The executor only runs `approved` actions.
* **Integration:** the routine runs on a schedule (e.g. every 10 min during the analyst's shift) and talks to our API through a thin **MCP server** (tools: `list_my_queue`, `claim_next`, `get_case_bundle`, `add_enrichment`, `propose_actions`, `start_run`, `finish_run`), with plain REST as fallback. Each run is recorded (`/v1/bot/runs`) so the console can show "your bot handled 6 cases since 09:00".

## Consequences
The productivity story is clear and safe: the bot does the legwork, the human keeps authority. Requires the API to be reachable from the Grok Bot environment (tunnel or hosted VM).
