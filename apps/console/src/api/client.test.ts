import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { expect, test } from "vitest";
import { createApiClient } from "./client";
import { actions, alerts, auditEvents, cases, decisions, evidencePacks, nextStepsPacks, webhooks } from "./contract-examples";
import { mockBaseUrl } from "../test/mock-base-url";

const repoRoot = path.resolve(process.cwd(), "../..");

test("typed client reads contract examples from the Prism mock", async () => {
  const client = createApiClient({
    baseUrl: mockBaseUrl(),
    token: "dev-analyst",
    splunkToken: "dev-splunk-token",
  });

  const health = await client.GET("/v1/healthz");
  expect(dataOf(health)).toEqual({ status: "ok", db: "ok", agent: "ok" });

  const page = dataOf(await client.GET("/v1/cases"));
  expect(page).toEqual({
    items: [cases.escalated, cases.autoClosed],
    next_cursor: null,
  });

  const escalated = dataOf(
    await client.GET("/v1/cases/{case_id}", {
      params: { path: { case_id: cases.escalated.case_id } },
    }),
  );
  expect(escalated).toEqual(cases.escalated);

  const autoClosed = dataOf(
    await client.GET("/v1/cases/{case_id}", {
      params: { path: { case_id: cases.autoClosed.case_id } },
      headers: { Prefer: "example=auto-closed" },
    }),
  );
  expect(autoClosed).toEqual(cases.autoClosed);

  expect(
    dataOf(
      await client.GET("/v1/alerts/{alert_id}", {
        params: { path: { alert_id: alerts.escalate.alert_id } },
      }),
    ),
  ).toEqual(alerts.escalate);
  expect(
    dataOf(
      await client.GET("/v1/alerts/{alert_id}", {
        params: { path: { alert_id: alerts.downgrade.alert_id } },
        headers: { Prefer: "example=downgrade" },
      }),
    ),
  ).toEqual(alerts.downgrade);

  expect(
    dataOf(
      await client.GET("/v1/alerts/{alert_id}/decision", {
        params: { path: { alert_id: decisions.escalate.alert_id } },
      }),
    ),
  ).toEqual(decisions.escalate);
  expect(
    dataOf(
      await client.GET("/v1/alerts/{alert_id}/decision", {
        params: { path: { alert_id: decisions.downgrade.alert_id } },
        headers: { Prefer: "example=downgrade" },
      }),
    ),
  ).toEqual(decisions.downgrade);
  expect(
    dataOf(
      await client.GET("/v1/alerts/{alert_id}/decision", {
        params: { path: { alert_id: decisions.unchanged.alert_id } },
        headers: { Prefer: "example=unchanged" },
      }),
    ),
  ).toEqual(decisions.unchanged);

  expect(
    dataOf(
      await client.GET("/v1/cases/{case_id}/evidence", {
        params: { path: { case_id: evidencePacks.escalated.case_id } },
      }),
    ),
  ).toEqual(evidencePacks.escalated);
  expect(
    dataOf(
      await client.GET("/v1/cases/{case_id}/next-steps", {
        params: { path: { case_id: nextStepsPacks.escalated.case_id } },
      }),
    ),
  ).toEqual(nextStepsPacks.escalated);

  const trail = [auditEvents.autoClosed, auditEvents.actionApproved].sort((a, b) => a.seq - b.seq);
  expect(
    dataOf(
      await client.GET("/v1/cases/{case_id}/audit", {
        params: { path: { case_id: cases.escalated.case_id } },
      }),
    ),
  ).toEqual(trail);

  expect(
    dataOf(
      await client.GET("/v1/cases/{case_id}/actions", {
        params: { path: { case_id: actions.approved.case_id } },
      }),
    ),
  ).toEqual([actions.approved]);
  expect(
    dataOf(
      await client.POST("/v1/cases/{case_id}/actions/{action_id}/approve", {
        params: {
          path: {
            case_id: actions.approved.case_id,
            action_id: actions.approved.action_id,
          },
        },
        body: { note: actions.approved.decision_note },
      }),
    ),
  ).toEqual(actions.approved);

  const accepted = dataOf(
    await client.POST("/v1/ingest/splunk/{instance}", {
      params: {
        path: { instance: "splunk-onprem-sg1" },
        query: { severity: 4 },
      },
      body: webhooks.escalate,
      headers: { Prefer: "code=202" },
    }),
  );
  expect(accepted).toEqual({
    alert_id: alerts.escalate.alert_id,
    status: "accepted",
    case_id: cases.escalated.case_id,
  });
});

test("every positive example file is referenced by the typed fixtures", () => {
  const examplesDir = path.join(repoRoot, "contracts/examples");
  const files = readdirSync(examplesDir).filter((file) => file.endsWith(".json")).sort();
  const referenced = [
    "action.approved.json",
    "alert.downgrade.json",
    "alert.escalate.json",
    "audit-event.action-approved.json",
    "audit-event.auto-closed.json",
    "case.auto-closed.json",
    "case.escalated.json",
    "evidence-pack.escalated.json",
    "next-steps-pack.escalated.json",
    "splunk-webhook.downgrade.json",
    "splunk-webhook.escalate.json",
    "triage-decision.downgrade.json",
    "triage-decision.escalate.json",
    "triage-decision.unchanged.json",
  ].sort();
  expect(files).toEqual(referenced);
  expect(readFileSync(path.join(examplesDir, "case.escalated.json"), "utf8")).toContain(cases.escalated.case_id);
});

function dataOf<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.data === undefined) {
    throw new Error(`HTTP ${result.response.status} ${JSON.stringify(result.error)}`);
  }
  return result.data;
}
