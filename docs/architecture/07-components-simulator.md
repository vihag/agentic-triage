# 07 Components: Splunk alert simulator

```mermaid
%% name: arch-07-components-simulator
flowchart LR
  P1(("CLI<br/>simulator send / burst / export"))
  subgraph S["Simulator container"]
    direction TB
    CLI["CLI"]
    LIB["Scenario library<br/>YAML: escalate, downgrade,<br/>unchanged-high, unchanged-low"]
    BLD["Payload builder<br/>Splunk webhook shape"]
    CHK["Self-check<br/>validates vs splunk-webhook schema"]
    SND["Sender<br/>?token= & ?severity="]
    EXP["Golden exporter<br/>tests/golden fixtures"]
  end
  R1(("Triage API<br/>ingestSplunkAlert"))
  P1 --- CLI --> LIB --> BLD --> CHK --> SND --- R1
  CHK --> EXP
  classDef iface fill:#fff,stroke:#1168bd,stroke-width:2px,color:#1168bd
  class P1,R1 iface
```

**Caption.** Stands in for on-prem Splunk in the demo and in tests. It builds payloads with the same body
shape as Splunk's Webhook alert action, checks each against `SplunkWebhookPayload`
(`contracts/schemas/splunk-webhook.schema.json`) before sending, and calls `ingestSplunkAlert` with the
per-instance token and the severity URL parameter (confirmed input method, ADR-0005). The same builder exports
the golden-alert fixtures, so the agent's golden tests and the live demo use identical inputs.
