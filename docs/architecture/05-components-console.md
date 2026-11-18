# 05 Components: Analyst console

```mermaid
%% name: arch-05-components-console
flowchart LR
  P1(("UI routes<br/>/queue /cases/:id /approvals /bot-activity"))
  subgraph C["Analyst console container (React + Vite + TS)"]
    direction TB
    AUTH["OIDC session"]
    QV["QueueView"]
    CD["CaseDetail"]
    DX["DecisionExplainer"]
    EV["EvidenceTimeline"]
    NS["NextStepsPanel + drafts"]
    AI["ApprovalsInbox"]
    AT["AuditTimeline"]
    BA["BotActivity<br/>runs on my behalf"]
    Q["TanStack Query cache"]
    CL["Generated API client<br/>openapi-typescript"]
  end
  R1(("Triage API<br/>analyst operations"))
  R2(("IdP OIDC"))
  P1 --- QV & CD & AI
  CD --> DX & EV & NS & AT
  NS --> AI
  P1 --- BA
  QV & CD & AI & AT & BA --> Q --> CL
  CL --- R1
  AUTH --- R2
  AUTH --> CL
  classDef iface fill:#fff,stroke:#1168bd,stroke-width:2px,color:#1168bd
  class P1,R1,R2 iface
```

**Caption.** The console's pages and widgets. They all reach the API through one client generated from
`contracts/openapi.yaml`, so any contract drift becomes a TypeScript compile error. Required operations:
`listCases`, `getCase`, `getTriageDecision`, `getEvidencePack`, `getNextStepsPack`, `getCaseAudit`,
`claimNext`, `releaseCase`, `assignCase`, `transitionCase`, `listActions`, `proposeAction`,
`approveAction`, `rejectAction`, `listBotRuns` (bot activity view, closed gap 2). Verified consumer-side with Pact (consumer-driven contract) and developed
against a Prism mock server that serves `contracts/examples`. Approve/reject are only sent with the analyst's
OIDC token (`analystAuth`).
