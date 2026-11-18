# System architecture: C4 level 1 (context) and level 2 (containers)

## Level 1: System context

```mermaid
C4Context
  title System Context: Agentic Triage on a legacy SIEM
  Person(analyst, "SOC Analyst", "Triages escalated cases, approves or rejects proposed actions")
  Person(lead, "SOC Lead", "Tunes rules and policy, reviews auto-closed sample")
  System_Ext(splunk, "Splunk Enterprise (on-prem)", "Legacy SIEM. Saved searches fire the Webhook alert action")
  System(triage, "Agentic Triage", "Re-scores Splunk severity with rules + AI, auto-handles downgrades, queues escalations with evidence and next steps")
  System_Ext(grokbot, "Grok Bot (one per analyst)", "Scheduled routine that works the analyst's queue on their behalf and proposes next steps")
  System_Ext(llm, "LLM and embedding API", "Fuzzy matching judge and embeddings")
  System_Ext(tools, "Security tooling", "EDR, IdP, firewall, ticketing. Mocked in the demo")
  Rel(splunk, triage, "POST alert", "HTTPS webhook JSON")
  Rel(triage, llm, "Embed and judge", "HTTPS")
  Rel(analyst, triage, "Triage and approve", "Browser")
  Rel(lead, triage, "Configure, audit", "Browser")
  Rel(grokbot, triage, "Claim, enrich, propose", "REST or MCP, bot API key")
  Rel(triage, tools, "Execute approved actions only", "HTTPS")
  Rel(triage, splunk, "Read-only drill-down searches", "Splunk REST")
  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

## Level 2: Containers

```mermaid
C4Container
  title Containers: Agentic Triage
  Person(analyst, "SOC Analyst")
  System_Ext(splunk, "Splunk Enterprise", "Webhook alert action")
  System_Ext(grokbot, "Grok Bot routine", "Per analyst")
  System_Ext(llm, "LLM / embeddings")
  System_Ext(tools, "Security tooling (mock)")
  System_Boundary(sys, "Agentic Triage") {
    Container(console, "Analyst Console", "React, Vite, TypeScript", "Queue, case detail, approvals inbox, audit")
    Container(api, "Triage API", "Python 3.12, FastAPI", "Ingest, cases, actions, bot endpoints, auth")
    Container(worker, "Triage Worker", "Python, embeds triage-agent library", "Rules + fuzzy match, routing, evidence and next-steps packs")
    Container(executor, "Action Executor", "Python", "Runs approved actions through connectors")
    Container(mcp, "Triage MCP server", "Python, MCP", "Thin tool wrapper over bot endpoints for Grok Bot")
    ContainerDb(db, "Postgres 16 + pgvector", "SQL", "Alerts, cases, queue, actions, audit chain, incident embeddings")
  }
  Rel(splunk, api, "POST /v1/ingest/splunk/{instance}", "HTTPS")
  Rel(analyst, console, "Uses", "HTTPS")
  Rel(console, api, "REST /v1", "JSON, JWT")
  Rel(grokbot, mcp, "Tools", "MCP")
  Rel(mcp, api, "REST /v1/bot", "X-GrokBot-Key")
  Rel(api, db, "Read/write", "SQL")
  Rel(worker, db, "Outbox poll, write decisions", "SQL, SKIP LOCKED")
  Rel(worker, llm, "Embed, judge", "HTTPS")
  Rel(executor, db, "Poll approved actions", "SQL")
  Rel(executor, tools, "Execute", "HTTPS")
  UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

### Same containers, presentation layout (flowchart)

Mermaid's C4 renderer lays out edges loosely; this flowchart is the one to put on a slide.

```mermaid
flowchart LR
  SPL["Splunk Enterprise<br/>(on-prem, Webhook action)"]
  AN(["SOC Analyst"])
  GB(["Grok Bot routine<br/>one per analyst"])
  LLM["LLM / embeddings"]
  TOOLS["EDR / IdP / firewall / ticketing<br/>(mock)"]
  subgraph SYS["Agentic Triage"]
    API["Triage API<br/>FastAPI"]
    WRK["Triage Worker<br/>rules + fuzzy + routing + packs"]
    EXE["Action Executor<br/>approved only"]
    MCP["Triage MCP server<br/>bot tools, no approve"]
    CON["Analyst Console<br/>React + Vite + TS"]
    DB[("Postgres 16 + pgvector<br/>alerts, cases, queue, actions, audit")]
  end
  SPL -->|"POST /v1/ingest/splunk"| API
  AN --> CON -->|"REST + JWT"| API
  GB -->|MCP| MCP -->|"REST /v1/bot + X-GrokBot-Key"| API
  API <--> DB
  WRK <-->|"outbox, SKIP LOCKED"| DB
  WRK --> LLM
  EXE <-->|"approved actions"| DB
  EXE --> TOOLS
```

### Container responsibilities

| Container | Responsibility | Contract it implements |
|---|---|---|
| Analyst Console | Human UI; only place approvals happen | consumes `openapi.yaml` |
| Triage API | AuthN/Z, validation, state machine, audit emission | `openapi.yaml`, all schemas |
| Triage Worker | Async triage of each alert (outbox pattern) | `contracts/agent/interfaces.py`, `triage-decision`, packs |
| Action Executor | Executes `approved` actions only, records result | `action.schema.json` |
| Triage MCP server | Lets a Grok Bot use the bot API as tools | `openapi.yaml#tag/bot` |
| Postgres + pgvector | Durable state, queue, audit chain, vector index | ER diagram |

### Key quality attributes

* **Never lose an alert:** ingest writes alert + outbox row in one transaction, returns 202, idempotent on `sid`.
* **Explainability:** every decision stores all rule results and the similar items used.
* **Safety:** nothing external happens without an analyst approval; downgrades are auditable and re-openable.
* **Swappable AI:** fuzzy matcher and LLM sit behind Protocols; CI runs on mocks only.
