# 09 Data flow diagram, level 1

```mermaid
%% name: arch-09-dfd-level-1
flowchart TB
  SPL["Splunk"]
  LLM["LLM provider"]
  AN["Analyst browser"]
  GB["Grok Bot"]
  TOOLS["Security tooling"]
  subgraph BE["Trust boundary: our backend"]
    subgraph J1["J1 machine-driven"]
      P1(("1 Ingest"))
      D1[("D1 alerts")]
      D2[("D2 triage_outbox")]
      P2(("2 Triage"))
      D8[("D8 incident corpus")]
      D3[("D3 decisions")]
    end
    subgraph SHARED["Hand-off stores"]
      D4[("D4 cases / queue")]
      D5[("D5 evidence + next steps")]
      D6[("D6 actions")]
    end
    subgraph J2["J2 analyst-assisted"]
      P3(("3 Case + queue mgmt"))
      P4(("4 Bot adapter"))
      P5(("5 Action execution"))
    end
    D7[("D7 audit_events<br/>written by 1, 2, 3, 5")]
  end
  SPL -->|SplunkWebhookPayload| P1
  P1 -->|Alert| D1
  P1 -->|alert_id| D2
  D2 & D1 --> P2
  D8 -->|neighbours| P2
  P2 <-->|redacted text / judgement| LLM
  P2 -->|TriageDecision| D3
  P2 -->|Case| D4
  P2 -->|EvidencePack, NextStepsPack| D5
  P2 -->|"ProposedAction (proposed)"| D6
  D4 & D5 --> P3
  P3 -->|status, claims| D4
  P3 -->|approve / reject| D6
  AN <-->|cases, approvals| P3
  GB <-->|MCP tools| P4
  P4 <-->|bot operations| P3
  D6 -->|approved| P5
  P5 <-->|commands / results| TOOLS
  P3 -.->|AuditEvent| D7
```

**Caption.** DFD level 1 inside our backend trust boundary: five processes, eight data stores, and each
flow labelled with the JSON Schema it carries. The external entities sit in their own trust boundaries
exactly as in [level 0](08-dfd-level-0.md) (on-prem Splunk and tooling, analyst browser, Grok Bot cloud,
LLM provider); they are left unboxed here so the diagram fits one slide. It shows where data lands (D1-D8) and which process writes it. Process 2
(triage) is the only one that talks to the LLM provider, and process 5 is the only one that talks to security
tooling. Every process writes `AuditEvent`s to D7 (append-only, hash-chained; chain-verifier test). The
J1/J2 split is drawn explicitly: processes 1-2 are journey J1 (machine-driven), processes 3-5 are journey J2
(analyst-assisted), and they share only the hand-off stores D4-D6, i.e. the `Case`, `EvidencePack`,
`NextStepsPack` and `ProposedAction` contracts.
