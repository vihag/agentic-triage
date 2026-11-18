# Sequence: Splunk alert → agent → escalate → human-assisted triage queue

```mermaid
sequenceDiagram
  autonumber
  participant S as Splunk (on-prem)
  participant API as Triage API
  participant DB as Postgres
  participant W as Triage Worker
  participant RE as Rule engine
  participant FM as FuzzyMatcher
  participant LLM as LLM judge
  S->>API: POST /v1/ingest/splunk/sg1?token=...&severity=4 (webhook JSON)
  API->>API: validate splunk-webhook schema, map severity 4 -> medium
  API->>DB: BEGIN, INSERT alert (dedup on sid), INSERT triage_outbox, audit alert.received, COMMIT
  API-->>S: 202 {alert_id, status: accepted}
  W->>DB: claim outbox row (FOR UPDATE SKIP LOCKED)
  W->>RE: evaluate(alert, ctx)
  RE-->>W: RuleResult[] (AUTH-003 matched, floor=high)
  W->>FM: match(alert, k=5, timeout=5s)
  FM->>DB: pgvector kNN over incidents/patterns/baselines
  FM->>LLM: judge(alert, neighbours) -> JSON
  LLM-->>FM: suggested=high, conf=0.82
  FM-->>W: FuzzyMatchResult
  W->>W: combine_severity -> high (escalated), route -> enqueue_for_triage
  W->>W: build EvidencePack + NextStepsPack (actions status=proposed)
  W->>DB: BEGIN, INSERT decision, case(status=queued, queue=soc-high, assignee=priya), packs, actions
  W->>DB: audit triage.decided, case.created, case.queued, action.proposed, mark outbox done, COMMIT
  Note over DB: Case now visible in Priya's queue and to Priya's Grok Bot
```

Failure handling: the worker is idempotent on `alert_id` (unique decision per alert). A crash before COMMIT
leaves the outbox row unclaimed after its lease, so it is retried. A fuzzy timeout gives a rules-only
decision with guardrail `fuzzy_timeout_fallback`.
