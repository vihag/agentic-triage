# Sequence J1: Alert ingestion and agentic triage

```mermaid
%% name: uml-j1-sequence-alert-ingestion-triage
sequenceDiagram
  autonumber
  participant S as Splunk
  participant API as Triage API
  participant DB as Postgres
  participant W as Triage worker
  participant A as triage-agent
  participant L as LLM provider
  S->>API: ingestSplunkAlert (SplunkWebhookPayload, ?token, ?severity=4)
  API->>API: validate, map 4 to medium, normalise to Alert
  API->>DB: tx: insert Alert (unique sid) + triage_outbox + AuditEvent alert.received
  API-->>S: 202 IngestAccepted
  W->>DB: claim outbox row (FOR UPDATE SKIP LOCKED)
  W->>A: TriageAgent.triage(Alert, TriageContext)
  A->>A: RulePlugin.evaluate x N gives RuleResult[]
  A->>L: FuzzyMatcher.match uses LLMClient.complete_json (timeout 5s)
  L-->>A: FuzzyMatchResult (suggested severity, confidence)
  A->>A: combine_severity then RoutingPolicy.route
  A-->>W: TriageDecision
  alt escalated, or unchanged and at least medium
    W->>A: build_evidence_pack, build_next_steps
    A-->>W: EvidencePack, NextStepsPack (actions status=proposed)
    W->>DB: tx: TriageDecision + Case(queued, soc-high, assignee) + packs + AuditEvents
  else downgraded, confident, no guard rule
    W->>DB: tx: TriageDecision + Case(auto_closed) + AuditEvent case.auto_closed
  else downgraded otherwise
    W->>DB: tx: TriageDecision + Case(queued, soc-downgrade-review)
  else unchanged and below medium
    W->>DB: tx: TriageDecision + Case(auto_closed, recorded) + AuditEvent
  end
  W->>DB: mark outbox row done
  Note over DB: Hand-off to J2 is the Case contract only
```

**Caption.** Time-ordered J1. Each message names the contract it exercises: `ingestSplunkAlert` /
`SplunkWebhookPayload` / `IngestAccepted` (schema validation, Schemathesis), the `TriageAgent`, `RulePlugin`,
`FuzzyMatcher`, `LLMClient`, `RoutingPolicy` Protocols (Protocol mocks; golden alerts), and the persisted
`TriageDecision`, `Case`, `EvidencePack`, `NextStepsPack`, `AuditEvent` schemas (producer-side validation).
Failure behaviour: ingest is idempotent on `sid`; the worker is idempotent on `alert_id` and retries via the
outbox lease; a fuzzy timeout falls back to rules only and never auto-closes.
