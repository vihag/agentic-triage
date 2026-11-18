# 08 Data flow diagram, level 0

```mermaid
%% name: arch-08-dfd-level-0
flowchart LR
  subgraph TB1["Trust boundary: on-prem SOC network"]
    SPL["Splunk Enterprise"]
    TOOLS["Security tooling"]
  end
  subgraph TB2["Trust boundary: analyst browser"]
    AN["SOC Analyst"]
  end
  subgraph TB3["Trust boundary: Grok Bot cloud"]
    GB["Grok Bot routine"]
  end
  subgraph TB4["Trust boundary: LLM provider"]
    LLM["LLM / embeddings"]
  end
  subgraph TB5["Trust boundary: our backend"]
    P0(("0<br/>Agentic Triage"))
  end
  SPL -->|"alert payload (raw event fields)"| P0
  P0 -->|"drill-down search results request"| SPL
  P0 -->|"cases, decisions, evidence"| AN
  AN -->|"claims, approvals, resolutions"| P0
  P0 -->|"assigned cases"| GB
  GB -->|"enrichments, proposals, drafts"| P0
  P0 -->|"redacted alert text, neighbours"| LLM
  LLM -->|"embeddings, judgement JSON"| P0
  P0 -->|"approved action commands"| TOOLS
  TOOLS -->|"execution results"| P0
```

**Caption.** DFD level 0: the whole system is one process (0), with every data flow that crosses a trust
boundary. These are the five places to apply authentication, validation and redaction. Splunk → 0 uses a
per-instance token and is validated against `SplunkWebhookPayload`. Browser ↔ 0 uses `analystAuth` (OIDC JWT),
covered by Schemathesis + Pact. Grok Bot ↔ 0 uses `botApiKey`, scoped to one analyst, covered by Schemathesis
with a bot key and the bot-scope negative tests. 0 → LLM sends only redacted text through the `LLMClient`
Protocol (mocked in CI). 0 → tooling carries only `approved` `ProposedAction`s.
