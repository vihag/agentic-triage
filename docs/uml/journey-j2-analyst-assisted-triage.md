# Journey J2: Analyst-assisted triage (SOC analyst + Grok Bot in the console)

```mermaid
%% name: uml-j2-journey-analyst-assisted-triage
flowchart TB
  START[("Case queued, assigned to analyst<br/>(produced by J1)")]
  subgraph L1["Grok Bot routine (on analyst's behalf)"]
    G1["Scheduled run starts"]
    G2["Claim my newest assigned cases,<br/>read case bundle"]
    G3["Enrich: Splunk drill-down,<br/>identity, asset, threat intel"]
    G4["Draft comms, propose actions"]
  end
  subgraph L2["Analyst console"]
    U1["My queue: cases assigned to me,<br/>Splunk vs final severity"]
    U2["Case detail: decision explanation,<br/>evidence, bot proposals"]
    U3["Approvals inbox"]
  end
  subgraph L3["SOC Analyst"]
    H1["Opens queue"]
    H2{"Approve or reject<br/>each proposal"}
    H3["Resolve case:<br/>contained / FP / benign"]
  end
  subgraph L4["Triage API + executor"]
    S1["Case → awaiting_approval"]
    S2["Executor runs approved action,<br/>records result"]
    S3[("Case resolved → closed<br/>full audit trail")]
  end
  START --> G1 --> G2 --> G3 --> G4 --> S1
  START --> U1
  H1 --> U1 --> U2 --> U3 --> H2
  S1 --> U3
  H2 -->|approve| S2 --> H3
  H2 -->|reject with note| H3
  H3 --> S3
  classDef store fill:#e8f5e9,stroke:#2f7d4f
  class START,S3 store
```

**Caption.** Journey J2 in swimlanes by actor. It starts from a queued Case assigned to the analyst, which
is the only input it takes from J1. The analyst's Grok Bot does the legwork (claim, enrich, propose); the
analyst decides in the console; only analyst-approved actions run. Contracts: bot side `botStartRun`,
`botClaim`, `botGetCaseBundle`, `botAddEnrichment`, `botPropose`, `botFinishRun` behind the MCP adapter (Schemathesis with a bot
key, MCP tool tests vs Prism mock); console side `listCases`, `listBotRuns`, `getCase`, `getTriageDecision`,
`getEvidencePack`, `getNextStepsPack`, `approveAction`, `rejectAction`, `transitionCase` (Pact consumer +
Schemathesis provider); invariant `ProposedAction.decided_by.type = analyst` (schema validation and the
bot → approve = 403 negative test).
