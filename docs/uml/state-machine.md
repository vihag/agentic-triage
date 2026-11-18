# State machine: alert / case lifecycle

Alert processing (pipeline) and case lifecycle (work item). Every transition emits an AuditEvent.
The API enforces exactly these transitions (409 otherwise).

```mermaid
stateDiagram-v2
  direction LR
  state "Alert pipeline" as AP {
    [*] --> received: webhook 202
    received --> triaging: worker claims outbox
    triaging --> decided: TriageDecision stored
    triaging --> received: lease expired (retry)
    decided --> [*]
  }
  AP --> queued: enqueue_for_triage / enqueue_downgrade_review
  AP --> auto_closed: auto_closed / recorded_only
  queued --> claimed: claim (analyst or bot on behalf), lease set
  claimed --> queued: release / lease expired
  claimed --> in_progress: start work
  in_progress --> awaiting_approval: action proposed
  awaiting_approval --> in_progress: all actions approved or rejected
  in_progress --> resolved: analyst resolves (true positive)
  in_progress --> false_positive: analyst marks FP
  claimed --> false_positive: analyst marks FP
  resolved --> closed: retention / lead sign-off
  false_positive --> closed
  auto_closed --> queued: re-open (analyst/lead) or 5 percent QA sample
  auto_closed --> closed
  closed --> [*]
```

| From → To | Who may do it |
|---|---|
| queued → claimed | analyst; grok_bot only if `assignee == on_behalf_of` |
| claimed → in_progress | claimant |
| in_progress → awaiting_approval | system, when an action enters `proposed` |
| awaiting_approval → in_progress | system, when no action is `proposed` |
| * → resolved / false_positive | **analyst only** |
| auto_closed → queued | analyst or lead |
| claimed → queued | claimant, or reaper on lease expiry |

## Action lifecycle

```mermaid
stateDiagram-v2
  [*] --> proposed: agent, bot or analyst proposes
  proposed --> approved: analyst approves
  proposed --> rejected: analyst rejects
  proposed --> expired: case closed or TTL
  approved --> executing: executor picks up
  executing --> executed
  executing --> failed
  rejected --> [*]
  expired --> [*]
  executed --> [*]
  failed --> [*]
```
