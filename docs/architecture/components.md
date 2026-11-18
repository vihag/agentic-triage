# Component architecture (C4 level 3)

## Triage API (FastAPI)

```mermaid
flowchart TB
  subgraph API["Triage API (FastAPI)"]
    direction TB
    AUTH["Auth middleware<br/>analystAuth JWT / botApiKey / splunkToken<br/>-> Principal"]
    ING["Ingest router<br/>/v1/ingest/splunk"]
    NORM["Splunk normaliser<br/>severity map, entity extraction, dedup_key"]
    CASES["Cases router<br/>/v1/cases, /v1/queue/claim"]
    SM["Case state machine<br/>legal transitions + If-Match"]
    ACT["Actions router<br/>propose / approve / reject"]
    GUARD["Approval guard<br/>approver must be analyst principal"]
    BOT["Bot router<br/>/v1/bot/*"]
    SCOPE["Bot scope filter<br/>assignee == on_behalf_of"]
    REPO["Repositories (Data role)"]
    AUD["Audit writer (hash chain)"]
  end
  AUTH --> ING & CASES & ACT & BOT
  ING --> NORM --> REPO
  CASES --> SM --> REPO
  ACT --> GUARD --> REPO
  BOT --> SCOPE --> SM
  SCOPE --> ACT
  REPO --> AUD
  REPO --> PG[(Postgres)]
```

## Triage Worker + triage-agent library

```mermaid
flowchart TB
  subgraph W["Triage Worker"]
    POLL["Outbox poller<br/>FOR UPDATE SKIP LOCKED"]
    ORCH["Triage orchestrator<br/>idempotent per alert_id"]
    ROUTER["Case router<br/>queue + assignee (round robin on shift)"]
  end
  subgraph A["triage-agent library (contracts/agent/interfaces.py)"]
    RE["Rule engine"]
    RP1["RulePlugin AUTH-003"]
    RP2["RulePlugin CROWN-001"]
    RPn["RulePlugin ..."]
    FM["FuzzyMatcher<br/>pgvector kNN"]
    LLM["LLMClient<br/>judge, structured JSON"]
    COMB["combine_severity<br/>rules clamp AI"]
    POL["RoutingPolicy"]
    EVB["EvidencePack builder"]
    NSB["NextStepsPack builder<br/>playbooks"]
  end
  POLL --> ORCH --> RE
  RE --> RP1 & RP2 & RPn
  ORCH --> FM --> LLM
  RE --> COMB
  FM --> COMB --> POL
  POL -->|enqueue_*| EVB --> NSB
  POL --> ROUTER
  NSB --> ROUTER
  ROUTER --> PG[(Postgres)]
```

## Analyst Console (React + Vite + TS)

```mermaid
flowchart LR
  subgraph C["Analyst Console"]
    CL["Generated API client<br/>openapi-typescript + TanStack Query"]
    QV["QueueView<br/>filters, Splunk vs final severity"]
    CD["CaseDetail"]
    DX["DecisionExplainer<br/>rule results, similar incidents"]
    EV["EvidenceTimeline"]
    NS["NextSteps + Drafts"]
    AI["ApprovalsInbox<br/>bot-proposed badge"]
    AT["AuditTimeline"]
    BA["BotActivity<br/>runs per analyst"]
  end
  QV --> CD --> DX & EV & NS & AT
  NS --> AI
  QV & CD & AI & AT & BA --> CL
  CL -->|REST + JWT| API[Triage API]
  CL -.dev.-> PRISM[Prism mock of openapi.yaml]
```

## Action Executor and Triage MCP server

```mermaid
flowchart LR
  subgraph E["Action Executor"]
    EP["Poller: status = approved"]
    DISP["Dispatcher by action.type"]
    C1["EDR connector (mock)"]
    C2["IdP connector (mock)"]
    C3["Firewall connector (mock)"]
    C4["Ticketing connector (mock)"]
  end
  EP --> DISP --> C1 & C2 & C3 & C4
  DISP -->|executed / failed + audit| PG[(Postgres)]
  subgraph M["Triage MCP server"]
    T1["list_my_queue"] --> BAPI
    T2["claim_next"] --> BAPI
    T3["get_case_bundle<br/>case + evidence + next steps"] --> BAPI
    T4["add_enrichment"] --> BAPI
    T5["propose_actions"] --> BAPI
    T6["start_run / finish_run"] --> BAPI
  end
  BAPI["REST /v1/bot/* with X-GrokBot-Key"]
```

Note the MCP server deliberately exposes **no approve tool**. Even if it did, the API would refuse it (403).
