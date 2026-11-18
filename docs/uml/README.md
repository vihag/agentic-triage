# UML

Two distinct user journeys, joined **only** at the queue / `Case` contract:

| Journey | Who | Journey diagram | Sequence diagram |
|---|---|---|---|
| **J1** Alert ingestion and agentic triage | machines only: Splunk, API, worker, agent | [journey-j1-alert-ingestion-triage.md](journey-j1-alert-ingestion-triage.md) | [seq-j1-alert-ingestion-triage.md](seq-j1-alert-ingestion-triage.md) |
| **J2** Analyst-assisted triage | SOC analyst + their Grok Bot, in the console | [journey-j2-analyst-assisted-triage.md](journey-j2-analyst-assisted-triage.md) | [seq-j2-analyst-assisted-triage.md](seq-j2-analyst-assisted-triage.md) |

```
J1: Splunk → ingest → rules + fuzzy → decision ──► Case (queued | auto_closed) + packs ──► J2: bot + analyst → approve/reject → resolved
                                                   └── the only shared contract: Case, EvidencePack, NextStepsPack ──┘
```

Also here: [state machines](state-machine.md) (case, action) and the [ER diagram](er-diagram.md).

Retired from the first design pack: `user-journeys.md`, `seq-escalate.md`, `seq-downgrade.md`,
`seq-console-triage.md`, `seq-grokbot-routine.md`. Their content is now covered by J1 (escalate + downgrade
paths in one sequence) and J2 (bot routine + console review in one sequence).
