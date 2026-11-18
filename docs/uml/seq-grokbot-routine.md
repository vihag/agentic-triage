# Sequence: Grok Bot routine works the queue on behalf of an analyst

The routine is configured once per analyst, e.g. *"Every 10 minutes during my shift: claim my newest
triage cases, enrich them, draft comms and propose next steps for my approval. Never approve anything."*

```mermaid
sequenceDiagram
  autonumber
  participant R as Grok Bot routine (Priya's bot)
  participant M as Triage MCP server
  participant API as Triage API
  participant DB as Postgres
  participant SP as Splunk REST (read-only)
  actor P as Priya
  R->>M: start_run()
  M->>API: POST /v1/bot/runs (X-GrokBot-Key)
  API->>API: key -> {bot: grokbot-priya, on_behalf_of: priya}
  API-->>M: BotRun {run_id}
  R->>M: claim_next(queue=soc-high, max=3)
  M->>API: POST /v1/bot/claim
  API->>DB: SKIP LOCKED claim WHERE assignee = priya
  API-->>M: cases (status=claimed, claimed_by=grok_bot on behalf of priya)
  loop each claimed case
    R->>M: get_case_bundle(case_id)
    M->>API: GET case, decision, evidence, next-steps
    R->>SP: drill-down search (post-login activity for jdoe)
    R->>M: add_enrichment(identity_context, splunk_search, ...)
    M->>API: POST /v1/bot/cases/{id}/enrichments
    API->>DB: evidence pack v+1, audit evidence.appended (actor grok_bot / priya)
    R->>R: reason over evidence, choose playbook steps, draft comms
    R->>M: propose_actions([disable_user], drafts, summary)
    M->>API: POST /v1/bot/cases/{id}/proposals
    API->>DB: actions status=proposed, case -> awaiting_approval, audit action.proposed
  end
  R->>M: finish_run(summary)
  M->>API: PATCH /v1/bot/runs/{run_id}
  R-->>P: Notification "3 cases ready for your approval"
  P->>API: approve or reject in console (analystAuth only)
  Note over R,API: If the bot calls approve: 403 + auth.denied audit. The MCP server exposes no approve tool.
```

## Bot run states

```mermaid
stateDiagram-v2
  [*] --> running: POST /v1/bot/runs
  running --> succeeded: PATCH status=succeeded
  running --> partial: some cases failed
  running --> failed: error / timeout
  succeeded --> [*]
  partial --> [*]
  failed --> [*]
```
