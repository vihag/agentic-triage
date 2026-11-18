# ER diagram (Postgres)

Owner: Data/DB engineer. JSONB columns hold sub-documents whose shape is fixed by the JSON Schemas.

```mermaid
%% name: uml-er-diagram
erDiagram
  SIEM_INSTANCE ||--o{ ALERT : sends
  ALERT ||--|| TRIAGE_OUTBOX : "queued for triage"
  ALERT ||--o| TRIAGE_DECISION : "decided by"
  CASE ||--|{ ALERT : groups
  TRIAGE_DECISION ||--|| CASE : creates
  CASE ||--o| EVIDENCE_PACK : has
  EVIDENCE_PACK ||--|{ EVIDENCE_ITEM : contains
  CASE ||--o| NEXT_STEPS_PACK : has
  CASE ||--o{ ACTION : "has proposed"
  ANALYST ||--o{ CASE : "assigned"
  ANALYST ||--o{ BOT_CREDENTIAL : owns
  BOT_CREDENTIAL ||--o{ BOT_RUN : performs
  CASE ||--o{ AUDIT_EVENT : "audited by"
  INCIDENT_CORPUS ||--o{ TRIAGE_DECISION : "matched in"
  RULE ||--o{ TRIAGE_DECISION : "evaluated in"

  SIEM_INSTANCE {
    text instance_id PK
    text kind "splunk|simulator"
    text token_hash
    text base_url
  }
  ALERT {
    uuid alert_id PK
    text instance_id FK
    text sid UK
    text search_name
    text splunk_severity
    timestamptz received_at
    timestamptz event_time
    text title
    jsonb entities
    text dedup_key
    uuid case_id FK
    jsonb raw
  }
  TRIAGE_OUTBOX {
    bigserial id PK
    uuid alert_id FK
    text status "pending|processing|done|dead"
    int attempts
    timestamptz lease_expires_at
  }
  TRIAGE_DECISION {
    uuid decision_id PK
    uuid alert_id FK,UK
    text original_severity
    text final_severity
    text direction
    text disposition
    numeric confidence
    jsonb candidate_labels
    jsonb rule_results
    jsonb fuzzy_result
    jsonb policy
    text agent_version
    timestamptz decided_at
  }
  CASE {
    uuid case_id PK
    uuid decision_id FK
    text title
    text severity
    text original_severity
    text direction
    text status
    text queue
    int priority
    text assignee FK
    jsonb claimed_by
    timestamptz lease_expires_at
    jsonb candidate_labels
    jsonb resolution
    int version
    timestamptz created_at
    timestamptz updated_at
  }
  EVIDENCE_PACK {
    uuid evidence_pack_id PK
    uuid case_id FK,UK
    int version
    text summary
    jsonb timeline
    jsonb generated_by
  }
  EVIDENCE_ITEM {
    text evidence_id PK
    uuid evidence_pack_id FK
    text kind
    text title
    text source
    jsonb added_by
    jsonb data
    timestamptz collected_at
  }
  NEXT_STEPS_PACK {
    uuid next_steps_pack_id PK
    uuid case_id FK,UK
    int version
    text playbook_id
    jsonb steps
    jsonb draft_responses
  }
  ACTION {
    uuid action_id PK
    uuid case_id FK
    text type
    jsonb params
    text risk
    text status
    jsonb proposed_by
    jsonb decided_by
    timestamptz decided_at
    jsonb execution_result
  }
  ANALYST {
    text analyst_id PK
    text display_name
    text email
    bool on_shift
  }
  BOT_CREDENTIAL {
    text bot_id PK
    text on_behalf_of FK
    text key_hash
    bool revoked
    timestamptz created_at
  }
  BOT_RUN {
    uuid run_id PK
    text bot_id FK
    text routine_id
    text status
    int cases_processed
    timestamptz started_at
    timestamptz finished_at
  }
  AUDIT_EVENT {
    bigserial seq PK
    uuid event_id UK
    timestamptz occurred_at
    text type
    jsonb actor
    uuid case_id FK
    uuid alert_id FK
    jsonb data
    text prev_hash
    text hash
  }
  INCIDENT_CORPUS {
    text ref_id PK
    text ref_type "past_incident|known_pattern|benign_baseline"
    text summary
    text verified_severity
    text verdict
    vector embedding "pgvector(1536)"
  }
  RULE {
    text rule_id PK
    text version PK
    bool enabled
    int priority
    jsonb config
  }
```

Key indexes: `cases (queue, status, priority DESC, created_at) WHERE status='queued'`; `cases (assignee, status)`;
`alerts (sid) UNIQUE`; `alerts (dedup_key) WHERE case open`; `triage_outbox (status, id)`; `actions (status) WHERE status='approved'`;
`incident_corpus USING hnsw (embedding vector_cosine_ops)`.

**Caption.** Physical data model in Postgres, owned by the Data/DB engineer. JSONB columns hold sub-documents
whose shape is fixed by the JSON Schemas (`TriageDecision.rule_results`, `Case.claimed_by`, `ProposedAction.params`,
...). The J1 → J2 hand-off is visible here: J1 writes `ALERT`, `TRIAGE_DECISION`, `CASE`, `EVIDENCE_PACK`,
`NEXT_STEPS_PACK` and `ACTION(proposed)`; J2 reads them and writes claims, enrichments, decisions and
`AUDIT_EVENT`s. Verified by DB round-trip tests (every example under `contracts/examples` is inserted and read
back, then validated against its schema), migration up/down tests, and the audit chain verifier.

