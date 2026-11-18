# Agentic Triage for legacy SIEMs (Splunk)

> Phase 1 deliverable: **design pack + contracts**. No application code yet beyond contract stubs.
> Build challenge for SpaceX-SI Field Engineering / Solutions Architect, demo Mon 23 Nov 2026.

## What it does

A legacy on-prem **Splunk** fires an alert through its Webhook alert action. Our **Triage Agent** re-scores
the severity Splunk assigned, using **deterministic rules** first and **AI fuzzy matching** second
(pgvector similarity against past incidents, known patterns and benign baselines, plus an LLM judge).

* **Severity goes up:** candidate label + **Evidence Pack** + **Suggested Next Steps Pack**, then queued for human-assisted triage.
* **Severity goes down:** auto-handled (auto-closed with an audit record, one click to re-open). Low-confidence or guarded downgrades go to a review queue instead.
* **Unchanged:** medium and above go to the queue at standard priority; below medium is recorded and closed.

For the escalated queue each SOC analyst is **10x-ed by a Grok Bot routine** that runs on their behalf:
it claims the newest cases assigned to them, enriches them, drafts comms and **proposes** actions. Only the
analyst can **approve**. That rule is enforced in the OpenAPI contract, the API and the JSON Schema.

```mermaid
%% name: overview-flow
flowchart LR
  S[Splunk alert] --> I[Ingest API] --> W[Triage Agent<br/>rules + fuzzy]
  W -->|down, confident| AC[Auto-close + audit]
  W -->|up / unchanged high| Q[(Triage queue)]
  Q --> B[Analyst's Grok Bot<br/>enrich + propose]
  B --> H{Analyst approves?}
  H -->|yes| X[Execute action]
  H -->|no| R[Reject, note]
```

**Caption.** The whole product on one line: journey J1 (Splunk → agent → auto-close or queue) feeds journey J2 (Grok Bot proposes, analyst decides). The detailed, single-purpose diagrams are indexed in [docs/architecture](docs/architecture/README.md) and [docs/uml](docs/uml/README.md); contracts per boundary are in [contracts-map.md](docs/architecture/contracts-map.md).

## How the team is organised

Seven roles, each owning code **and** contracts: Architect/Tech Lead, Backend, Triage-Agent/ML, Frontend,
Data/DB, QA/contract-test, DevOps. See [docs/team.md](docs/team.md) for the ownership matrix and definitions
of done, and [docs/plan.md](docs/plan.md) for milestones M0-M5 and 25 tickets (also as
[plan/issues.json](plan/issues.json), ready for `gh issue create`).

Work is **contract-first** ([ADR-0007](docs/adr/0007-contract-first-development.md)): contracts were fixed
before any code, so the console builds against a Prism mock, the agent against mocked AI, and the API
against the schemas, all in parallel.

## Repo layout

```
contracts/
  openapi.yaml               OpenAPI 3.1 for the backend API (ingest, cases, queue, actions, bot)
  schemas/*.schema.json      JSON Schema 2020-12: Alert, TriageDecision, EvidencePack, NextStepsPack,
                             Case, AuditEvent, ProposedAction, SplunkWebhookPayload, common
  examples/*.json            positive examples (<schema>[.<Def>].<variant>.json)
  examples/invalid/*.json    negative examples that must fail (pin invariants)
  agent/interfaces.py        triage agent Protocols: RulePlugin, FuzzyMatcher, LLMClient, RoutingPolicy, mocks
  agent/README.md            agent I/O, pipeline, mocking, non-functional contract
docs/
  architecture/README.md     index of the 10 single-purpose architecture diagrams
  uml/README.md              index of journeys J1/J2, sequences, state machines, ER
  team.md                    roles, ownership boundaries, contracts owned/consumed, DoD
  plan.md                    milestones, dependency graph, tickets (generated section)
  testing.md                 contract-first test strategy + CI outline
  architecture/              01 context, 02 containers/deployment, 03-07 components per container,
                             08-09 DFD level 0/1 with trust boundaries, contracts-map.md (10)
  adr/                       0001-0008 architecture decision records
  uml/                       J1 + J2 journeys and sequences, state machines, ER diagram
  rendered/                  every mermaid block as <name>.svg and <name>.png (2x, slide-ready)
plan/tickets.yaml            source of truth for tickets -> plan/issues.json
scripts/validate_contracts.py  the contract gate (CI-blocking)
scripts/gen_issues.py        regenerate issues.json + plan.md tickets
scripts/render_mermaid.sh    render docs mermaid to SVG
.github/workflows/contracts.yml  CI: contract gate + mermaid render
```

## Run the contract tests

```bash
make contracts          # creates .venv, installs requirements-dev.txt, runs scripts/validate_contracts.py
# or
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python scripts/validate_contracts.py
```

The gate checks: schemas are valid; every example validates; every invalid example is rejected;
OpenAPI 3.1 is valid with external `$ref`s resolved plus house lint (approve/reject analyst-only,
bot endpoints bot-key-only); the agent interface imports and its routing policy and `combine_severity`
reproduce the example decisions; `plan/issues.json` is in sync.

Render diagrams (needs `@mermaid-js/mermaid-cli`): `make diagrams` writes `docs/rendered/<name>.svg` and `<name>.png` (2x). Names come from a `%% name:` comment on the first line of each mermaid block. Set `MMDC=` and `CHROME_PATH=` if needed.

## Where to start reading

1. [Architecture index](docs/architecture/README.md): context, containers, components, DFDs, [contract map](docs/architecture/contracts-map.md)
2. The two user journeys: [J1 alert ingestion and agentic triage](docs/uml/journey-j1-alert-ingestion-triage.md) and [J2 analyst-assisted triage](docs/uml/journey-j2-analyst-assisted-triage.md), each with a sequence diagram ([J1](docs/uml/seq-j1-alert-ingestion-triage.md), [J2](docs/uml/seq-j2-analyst-assisted-triage.md))
3. [ADR-0005 severity re-scoring and routing](docs/adr/0005-severity-rescoring-and-routing-policy.md)
4. [ADR-0006 Grok Bot + human approval](docs/adr/0006-grok-bot-routines-and-human-approval.md)
5. [contracts/openapi.yaml](contracts/openapi.yaml)
