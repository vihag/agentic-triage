# 06 Components: Bot MCP adapter

```mermaid
%% name: arch-06-components-bot-mcp-adapter
flowchart LR
  P1(("MCP tools<br/>list_my_queue, claim_next,<br/>add_enrichment, propose_actions,<br/>start_run, finish_run"))
  subgraph M["Bot MCP adapter container"]
    direction TB
    SRV["MCP server<br/>tool schemas"]
    MAP["Tool → operation mapper<br/>1:1, no extra logic"]
    KEY["Credential holder<br/>X-GrokBot-Key from env"]
    CL["Generated REST client<br/>bot tag only"]
  end
  R1(("Triage API<br/>bot operations"))
  P1 --- SRV --> MAP --> CL --- R1
  KEY --> CL
  classDef iface fill:#fff,stroke:#1168bd,stroke-width:2px,color:#1168bd
  class P1,R1 iface
```

**Caption.** A deliberately thin adapter that lets a Grok Bot routine use the bot API as MCP tools.
Each tool maps 1:1 to an OpenAPI operation: `list_my_queue` → `botListQueue`, `claim_next` → `botClaim`,
`add_enrichment` → `botAddEnrichment`, `propose_actions` → `botPropose`, `start_run` → `botStartRun`,
`finish_run` → `botFinishRun`. There is **no approve tool**, and the API would return 403 anyway. Tests:
MCP tool-schema tests plus the adapter running against a Prism mock (consumer-side), and Schemathesis with a
bot key on the provider side. Open item: a bot-readable case bundle (evidence + next steps) is not in the bot
tag yet. See [contracts-map.md](contracts-map.md).
