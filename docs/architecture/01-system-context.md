# 01 System context

```mermaid
%% name: arch-01-system-context
flowchart LR
  AN(["SOC Analyst<br/><i>person</i>"])
  LEAD(["SOC Lead<br/><i>person</i>"])
  SPL["Splunk Enterprise<br/><i>external system, on-prem</i>"]
  GB["Grok Bot routine<br/><i>external system, one per analyst</i>"]
  LLM["LLM and embedding provider<br/><i>external system</i>"]
  IDP["Identity provider (OIDC)<br/><i>external system</i>"]
  TOOLS["Security tooling<br/>EDR, IdP admin, firewall, ticketing<br/><i>external, mocked in demo</i>"]
  SYS["<b>Agentic Triage</b><br/>re-scores Splunk alerts, auto-handles downgrades,<br/>queues escalations for analyst + bot triage"]
  SPL -->|"alert webhook"| SYS
  SYS -.->|"read-only drill-down searches"| SPL
  AN -->|"works queue, approves actions"| SYS
  LEAD -->|"reviews downgrades, tunes policy"| SYS
  GB -->|"claims, enriches, proposes on analyst's behalf"| SYS
  SYS -->|"embed + judge"| LLM
  AN -.->|"signs in"| IDP
  SYS -->|"executes approved actions only"| TOOLS
  classDef ext fill:#eee,stroke:#888,color:#333
  classDef person fill:#08427b,stroke:#052e56,color:#fff
  classDef sys fill:#1168bd,stroke:#0b4884,color:#fff
  class SPL,GB,LLM,IDP,TOOLS ext
  class AN,LEAD person
  class SYS sys
```

**Caption.** C4 level 1: the system as one box, with the people and external systems it talks to.
There are no internal parts here (those are in [02](02-containers-deployment.md)). Each arrow crosses
a system boundary and is covered by an external contract: Splunk → system is `ingestSplunkAlert` with
`SplunkWebhookPayload` (schema validation + Schemathesis); analyst → system is the console's use of the
analyst operations (Pact consumer tests + Prism mock); Grok Bot → system is the `/v1/bot/*` operations via
the MCP adapter (Schemathesis + MCP tool tests against a Prism mock); system → LLM is the `LLMClient`
Protocol (Protocol mock in CI, nightly drift run). Tooling connectors have no contract yet; they are mocked
(see [contracts-map.md](contracts-map.md), open items).
