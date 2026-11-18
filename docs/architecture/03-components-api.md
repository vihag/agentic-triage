# 03 Components: Triage API

```mermaid
%% name: arch-03-components-api
flowchart LR
  subgraph PROV["Provided interfaces (OpenAPI operationIds)"]
    direction TB
    P1(("ingest"))
    P2(("alerts + cases"))
    P3(("actions"))
    P4(("bot"))
  end
  subgraph API["Triage API container"]
    direction TB
    AUTH["AuthN/Z<br/>JWT / bot key / Splunk token → Principal"]
    ING["Ingest router"]
    NORM["Splunk normaliser<br/>severity map, entities, dedup_key"]
    CASES["Alerts + cases routers"]
    SM["Case state machine<br/>+ If-Match"]
    ACT["Actions router"]
    GUARD["Approval guard<br/>approver must be analyst"]
    BOT["Bot router"]
    SCOPE["Bot scope filter<br/>assignee == on_behalf_of"]
    REPO["Repositories"]
    AUD["Audit writer<br/>hash chain"]
  end
  subgraph REQ["Required interfaces"]
    direction TB
    R1(("Postgres SQL<br/>schemas as rows"))
    R2(("IdP JWKS"))
  end
  P1 --- ING
  P2 --- CASES
  P3 --- ACT
  P4 --- BOT
  AUTH --> ING & CASES & ACT & BOT
  ING --> NORM --> REPO
  CASES --> SM --> REPO
  ACT --> GUARD --> REPO
  BOT --> SCOPE --> SM
  REPO --> AUD
  REPO --- R1
  AUTH --- R2
  classDef iface fill:#fff,stroke:#1168bd,stroke-width:2px,color:#1168bd
  class P1,P2,P3,P4,R1,R2 iface
```

**Caption.** Internal components of the API, with provided interfaces on the left and required ones on
the right. The provided interfaces are the OpenAPI tags: **ingest** = `ingestSplunkAlert`; **alerts + cases** =
`getAlert`, `getTriageDecision`, `listCases`, `getCase`, `getEvidencePack`, `getNextStepsPack`,
`getCaseAudit`, `claimNext`, `releaseCase`, `assignCase`, `transitionCase`; **actions** = `listActions`,
`proposeAction`, `approveAction`, `rejectAction`; **bot** = `botStartRun`, `botFinishRun`, `botListQueue`,
`botClaim`, `botAddEnrichment`, `botPropose`. Schemathesis tests every provided operation against
`openapi.yaml`, and Pact verifies the console's expectations. Two invariants live in named components so they
can be unit-tested on their own: the **Approval guard** (bot principal → 403 + `auth.denied`, checked by the
contract-gate lint and by an invalid `ProposedAction` example) and the **Bot scope filter**. The required SQL
interface is tested by round-tripping every schema example through the repositories.
