import type { components } from "./schema";
import actionApproved from "../../../../contracts/examples/action.approved.json";
import alertDowngrade from "../../../../contracts/examples/alert.downgrade.json";
import alertEscalate from "../../../../contracts/examples/alert.escalate.json";
import auditApproved from "../../../../contracts/examples/audit-event.action-approved.json";
import auditAutoClosed from "../../../../contracts/examples/audit-event.auto-closed.json";
import caseAutoClosed from "../../../../contracts/examples/case.auto-closed.json";
import caseEscalated from "../../../../contracts/examples/case.escalated.json";
import evidenceEscalated from "../../../../contracts/examples/evidence-pack.escalated.json";
import nextStepsEscalated from "../../../../contracts/examples/next-steps-pack.escalated.json";
import webhookDowngrade from "../../../../contracts/examples/splunk-webhook.downgrade.json";
import webhookEscalate from "../../../../contracts/examples/splunk-webhook.escalate.json";
import decisionDowngrade from "../../../../contracts/examples/triage-decision.downgrade.json";
import decisionEscalate from "../../../../contracts/examples/triage-decision.escalate.json";
import decisionUnchanged from "../../../../contracts/examples/triage-decision.unchanged.json";
import botRunFinished from "../../../../contracts/examples/bot-run.finished.json";
import botRunRunning from "../../../../contracts/examples/bot-run.running.json";
import caseBundleEscalated from "../../../../contracts/examples/case-bundle.escalated.json";

export const alerts = {
  downgrade: asSchema<components["schemas"]["alert.schema"]>(alertDowngrade),
  escalate: asSchema<components["schemas"]["alert.schema"]>(alertEscalate),
};

export const decisions = {
  downgrade: asSchema<components["schemas"]["triage-decision.schema"]>(decisionDowngrade),
  escalate: asSchema<components["schemas"]["triage-decision.schema"]>(decisionEscalate),
  unchanged: asSchema<components["schemas"]["triage-decision.schema"]>(decisionUnchanged),
};

export const cases = {
  autoClosed: asSchema<components["schemas"]["case.schema"]>(caseAutoClosed),
  escalated: asSchema<components["schemas"]["case.schema"]>(caseEscalated),
};

export const evidencePacks = {
  escalated: asSchema<components["schemas"]["evidence-pack.schema"]>(evidenceEscalated),
};

export const nextStepsPacks = {
  escalated: asSchema<components["schemas"]["next-steps-pack.schema"]>(nextStepsEscalated),
};

export const actions = {
  approved: asSchema<components["schemas"]["action.schema"]>(actionApproved),
};

export const auditEvents = {
  actionApproved: asSchema<components["schemas"]["audit-event.schema"]>(auditApproved),
  autoClosed: asSchema<components["schemas"]["audit-event.schema"]>(auditAutoClosed),
};

export const webhooks = {
  downgrade: asSchema<components["schemas"]["splunk-webhook.schema"]>(webhookDowngrade),
  escalate: asSchema<components["schemas"]["splunk-webhook.schema"]>(webhookEscalate),
};

export const botRuns = {
  finished: asSchema<components["schemas"]["bot-run.schema"]>(botRunFinished),
  running: asSchema<components["schemas"]["bot-run.schema"]>(botRunRunning),
};

export const caseBundles = {
  escalated: asSchema<components["schemas"]["case-bundle.schema"]>(caseBundleEscalated),
};

// JSON imports widen enums to string. scripts/validate_contracts.py is what checks the documents.
function asSchema<T>(value: object): T {
  return value as T;
}
