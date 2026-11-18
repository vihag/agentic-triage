# Architecture diagrams

Each file holds **one** single-purpose diagram plus a caption saying which contracts and tests apply.
Rendered SVG and PNG (2x, for slides) are in [`docs/rendered/`](../rendered/) under the name shown.

| # | Diagram | Rendered name |
|---|---|---|
| 01 | [System context](01-system-context.md): actors and external systems only | `arch-01-system-context` |
| 02 | [Containers and deployment](02-containers-deployment.md): processes and datastore only | `arch-02-containers-deployment` |
| 03 | [Components: Triage API](03-components-api.md) | `arch-03-components-api` |
| 04 | [Components: Triage worker + agent](04-components-triage-worker.md) | `arch-04-components-triage-worker` |
| 05 | [Components: Analyst console](05-components-console.md) | `arch-05-components-console` |
| 06 | [Components: Bot MCP adapter](06-components-bot-mcp-adapter.md) | `arch-06-components-bot-mcp-adapter` |
| 07 | [Components: Splunk simulator](07-components-simulator.md) | `arch-07-components-simulator` |
| 08 | [DFD level 0](08-dfd-level-0.md) with trust boundaries | `arch-08-dfd-level-0` |
| 09 | [DFD level 1](09-dfd-level-1.md) with data stores | `arch-09-dfd-level-1` |
| 10 | [Interface / contract map](contracts-map.md) with diagram and table | `arch-10-contract-map` |

User journeys, sequences, state machines and the ER diagram are in [`docs/uml/`](../uml/README.md).
The diagrams from the first design pack (one combined C4/components/deployment page) were retired in favour of these.
