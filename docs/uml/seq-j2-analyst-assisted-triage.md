# Sequence J2: Analyst-assisted triage

```mermaid
%% name: uml-j2-sequence-analyst-assisted-triage
sequenceDiagram
  autonumber
  actor P as SOC Analyst
  participant UI as Console
  participant B as Grok Bot routine
  participant M as Bot MCP adapter
  participant API as Triage API
  participant X as Action executor
  Note over API: Precondition: Case queued and assigned to P (from J1)
  B->>M: start_run, claim_next
  M->>API: botStartRun, botClaim (X-GrokBot-Key)
  API-->>M: Case[] claimed by grok_bot on behalf of P
  loop each claimed case
    B->>M: add_enrichment
    M->>API: botAddEnrichment
    API-->>M: EvidencePack (version + 1)
    B->>M: propose_actions (actions, drafts, summary)
    M->>API: botPropose
    API-->>M: NextStepsPack, Case now awaiting_approval
  end
  B->>M: finish_run
  M->>API: botFinishRun
  P->>UI: open My queue
  UI->>API: listCases(assignee=P), getCase, getTriageDecision, getEvidencePack, getNextStepsPack
  API-->>UI: Case, TriageDecision, EvidencePack, NextStepsPack
  P->>UI: approve one action, reject another with a note
  UI->>API: approveAction / rejectAction (analystAuth JWT)
  API->>API: approval guard: principal must be analyst
  API-->>UI: ProposedAction(approved / rejected, decided_by = P)
  X->>API: picks up approved actions (via DB)
  X-->>API: executed + result, AuditEvent action.executed
  P->>UI: resolve as true_positive_contained
  UI->>API: transitionCase(resolved, If-Match)
  API-->>UI: Case(resolved)
  Note over B,API: If the bot calls approveAction: 403 + AuditEvent auth.denied. The MCP adapter has no approve tool.
```

**Caption.** Time-ordered J2: the bot run first, then the analyst's review. Bot calls use `botApiKey` and
are scoped to the analyst (`botStartRun`, `botClaim`, `botAddEnrichment`, `botPropose`, `botFinishRun`;
Schemathesis with a bot key, MCP tool tests vs Prism mock). Console calls use `analystAuth` (`listCases`,
`getCase`, `getTriageDecision`, `getEvidencePack`, `getNextStepsPack`, `approveAction`, `rejectAction`,
`transitionCase`; Pact consumer + Schemathesis provider). The human-approval invariant is enforced by the
API's approval guard, checked by the OpenAPI lint in the contract gate and by
`contracts/examples/invalid/action.bot-approved.json`. Open item: the bot reads evidence and next steps
through a proposed `botGetCaseBundle` (see `docs/architecture/contracts-map.md`).
