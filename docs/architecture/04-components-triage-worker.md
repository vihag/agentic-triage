# 04 Components: Triage worker and triage-agent library

```mermaid
%% name: arch-04-components-triage-worker
flowchart LR
  subgraph W["Triage worker container"]
    direction TB
    POLL["Outbox poller<br/>SKIP LOCKED"]
    ORCH["Triage orchestrator<br/>idempotent per alert_id"]
    PERS["Case persister + router<br/>queue, assignee, audit"]
    subgraph LIB["triage-agent library"]
      direction TB
      AG(("TriageAgent"))
      RE["Rule engine"]
      RP(("RulePlugin"))
      RULES["Rule plugins<br/>AUTH-003, CROWN-001, ..."]
      FMI(("FuzzyMatcher"))
      FM["pgvector kNN matcher"]
      LC(("LLMClient"))
      COMB["combine_severity"]
      RPOL(("RoutingPolicy"))
      POL["DefaultRoutingPolicy"]
      PK["Pack builders<br/>evidence + next steps"]
    end
  end
  R1(("Postgres SQL"))
  R2(("LLM HTTPS"))
  POLL --> ORCH --> AG
  AG --- RE
  RE --> RP --- RULES
  AG --- FMI --- FM
  FM --> LC
  RE --> COMB
  FM --> COMB --> RPOL --- POL
  POL --> PK
  ORCH --> PERS
  POLL --- R1
  PERS --- R1
  FM --- R1
  LC --- R2
  classDef iface fill:#fff,stroke:#1168bd,stroke-width:2px,color:#1168bd
  class AG,RP,FMI,LC,RPOL,R1,R2 iface
```

**Caption.** The worker takes alerts from the outbox and calls the triage-agent library through the
`TriageAgent` Protocol. Inside the library, the circles are the Python Protocols in
`contracts/agent/interfaces.py`: `RulePlugin`, `FuzzyMatcher`, `LLMClient`, `RoutingPolicy`. Every AI-facing
seam is a Protocol, so CI swaps in `MockFuzzyMatcher` / `MockLLMClient` and runs the golden-alert suite
deterministically. The library's output must validate against `TriageDecision`, `EvidencePack` and
`NextStepsPack` (producer schema validation). `combine_severity` and `DefaultRoutingPolicy` are checked by the
contract gate against the ADR-0005 table and the example decisions. Required interfaces: Postgres
(`triage_outbox`, cases, pgvector corpus) and the LLM provider over HTTPS.
