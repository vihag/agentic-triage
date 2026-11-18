# ADR-0005: Severity re-scoring and routing policy

* Status: Accepted, **confirmed by Vihag 2026-11-18** · Date: 2026-11-18 · Owner: Architect, Triage-Agent/ML engineer

## Context
Splunk assigns a severity per saved search; it is static and noisy. We re-score each alert using deterministic rules and AI fuzzy matching, then route. AI must help but never be the only reason something dangerous is closed.

## Decision
**Scale:** 5 levels (`informational, low, medium, high, critical`). Splunk 1-6 map: 1,2 → informational, 3 → low, 4 → medium, 5 → high, 6 → critical.

**Combination order** (`combine_severity` in `contracts/agent/interfaces.py`):
1. Start at the Splunk severity.
2. Apply matched rules' `set`, then `delta` (±2 max).
3. Fuzzy matcher (kNN over past incidents / known patterns / benign baselines + LLM judge) may move the result **at most one level** toward its suggestion, and only if its confidence ≥ 0.75.
4. Clamp with matched rules' `floor` (max) and `ceiling` (min). **Rules always win over AI.**

Decision confidence = weighted mix of rule certainty and fuzzy confidence (implementation detail, recorded on the decision).

**Routing** (`DefaultRoutingPolicy`):

| Direction | Condition | Disposition | Case status / queue |
|---|---|---|---|
| escalated | always | `enqueue_for_triage` + candidate label(s) + Evidence Pack + Next Steps Pack | `queued` / `soc-high` (priority by severity + confidence) |
| downgraded | confidence ≥ 0.85 and no `never_auto_close` rule matched and fuzzy did not time out | `auto_closed` | `auto_closed`, resolution `auto_closed_downgrade`, audit event |
| downgraded | otherwise | `enqueue_downgrade_review` | `queued` / `soc-downgrade-review` (low priority) |
| unchanged | final ≥ medium | `enqueue_for_triage` (no candidate label, standard priority) | `queued` / `soc-high` or `soc-standard` |
| unchanged | final < medium | `recorded_only` | `auto_closed` with resolution note "recorded" |

**Guardrails:** `never_auto_close` rules (crown-jewel assets, privileged identities, active incident on the same entity); fuzzy timeout → rules-only + no auto-close; a 5 % random sample of auto-closed cases goes to the downgrade-review queue for drift monitoring; every auto-close is one click to re-open.

## Confirmed decisions (no longer open)

* **Unchanged-severity policy** (the two `unchanged` rows above): confirmed by Vihag, 2026-11-18.
* **Severity input from Splunk:** Splunk's Webhook action doesn't send the alert severity, so it comes from
  the webhook URL parameter `?severity=<1-6>` (e.g. `&severity=$alert.severity$`), or failing that a `severity`
  field the saved search evals into the result row. The URL parameter wins if both are present. Confirmed by
  Vihag, 2026-11-18. Contract: `ingestSplunkAlert` `severity` query parameter and
  `SplunkWebhookPayload.result.severity`.

## Consequences
Deterministic, testable core with AI as a bounded nudge; explanations are concrete (which rule, which similar incident). Thresholds live in config and are versioned in `policy.version`.
