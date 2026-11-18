# Journey J1: Alert ingestion and agentic triage (machine-driven, no human)

```mermaid
%% name: uml-j1-journey-alert-ingestion-triage
flowchart TB
  subgraph L1["Splunk (on-prem)"]
    A1["Saved search fires"]
    A2["Webhook alert action POSTs<br/>result row + ?severity="]
  end
  subgraph L2["Triage API: ingest"]
    B1["Validate + authenticate token"]
    B2["Normalise to Alert,<br/>dedup on sid"]
    B3["Store Alert + outbox,<br/>reply 202"]
  end
  subgraph L3["Triage worker + agent"]
    C1["Deterministic rules"]
    C2["AI fuzzy match<br/>similar incidents + LLM judge"]
    C3["combine_severity<br/>rules clamp AI"]
    C4{"Direction?"}
    C5["Build candidate label,<br/>Evidence Pack, Next Steps Pack"]
    C6{"Confident and<br/>no guard rule?"}
  end
  subgraph L4["Case store: hand-off to J2"]
    D1[("Case queued<br/>soc-high")]
    D2[("Case auto_closed<br/>+ AuditEvent")]
    D3[("Case queued<br/>soc-downgrade-review")]
  end
  A1 --> A2 --> B1 --> B2 --> B3 --> C1 --> C2 --> C3 --> C4
  C4 -->|"escalated, or unchanged ≥ medium"| C5 --> D1
  C4 -->|downgraded| C6
  C4 -->|"unchanged < medium"| D2
  C6 -->|yes| D2
  C6 -->|no| D3
  classDef store fill:#e8f5e9,stroke:#2f7d4f
  class D1,D2,D3 store
```

**Caption.** Journey J1 in swimlanes by actor. No human is involved: Splunk raises an alert, the API takes
it in, the worker re-scores it, and the journey ends in exactly one of three Case outcomes in the case store.
This is the only place J1 touches J2. Contracts on the way: `ingestSplunkAlert` with `SplunkWebhookPayload`
(schema validation, Schemathesis), the `Alert` schema, the agent Protocols `RulePlugin`, `FuzzyMatcher`,
`LLMClient`, `RoutingPolicy` (Protocol mocks, golden alerts), and at the end `TriageDecision`, `Case`,
`EvidencePack`, `NextStepsPack`, `AuditEvent` (producer-side schema validation). Routing follows ADR-0005,
including the confirmed unchanged-severity policy.
