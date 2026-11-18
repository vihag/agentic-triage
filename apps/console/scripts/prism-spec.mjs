// Builds a Prism mock document from contracts/openapi.yaml.
// contracts/ is not modified. Example payloads are copied in, and relative schema
// $refs are rewritten so Prism can resolve them from apps/console/.prism/.
// The default response is the `example` value. `Prefer: example=<variant>` selects
// a named example (the filename suffix, e.g. example=auto-closed).
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { dump, load } from "js-yaml";
import { packageRoot } from "./package-root.mjs";

const consoleRoot = packageRoot();
const repoRoot = path.resolve(consoleRoot, "../..");
const openapiPath = path.join(repoRoot, "contracts/openapi.yaml");
const examplesDir = path.join(repoRoot, "contracts/examples");
const defaultSpecPath = path.join(consoleRoot, ".prism/openapi.yaml");

const PREFERRED_VARIANTS = ["escalated", "escalate", "approved", "action-approved"];

const HTTP_METHODS = ["get", "post", "put", "patch", "delete"];

export function loadPositiveExamples() {
  return readdirSync(examplesDir)
    .filter((file) => file.endsWith(".json"))
    .sort()
    .map((file) => {
      const base = file.slice(0, -".json".length);
      const dot = base.indexOf(".");
      if (dot < 0) throw new Error(`example ${file} is missing a variant suffix`);
      return {
        file,
        schema: base.slice(0, dot),
        variant: base.slice(dot + 1),
        value: JSON.parse(readFileSync(path.join(examplesDir, file), "utf8")),
      };
    });
}

export function buildPrismSpec() {
  const spec = load(readFileSync(openapiPath, "utf8"));
  if (!spec || typeof spec !== "object") throw new Error("openapi.yaml did not parse");
  rewriteRelativeRefs(spec);
  const examples = groupExamples(loadPositiveExamples());
  const operations = operationsById(spec);
  const wired = new Set();

  const take = (schema) => {
    const list = examples.get(schema);
    if (!list?.length) throw new Error(`no positive examples for ${schema}`);
    return list;
  };
  const operation = (operationId) => {
    const found = operations.get(operationId);
    if (!found) throw new Error(`operationId ${operationId} is not in contracts/openapi.yaml`);
    wired.add(operationId);
    return found;
  };

  const alerts = take("alert");
  const decisions = take("triage-decision");
  const cases = take("case");
  const evidence = take("evidence-pack");
  const nextSteps = take("next-steps-pack");
  const audits = [...take("audit-event")].sort((a, b) => a.value.seq - b.value.seq);
  const actions = take("action");
  const webhooks = take("splunk-webhook");

  const caseItems = cases
    .map((example) => example.value)
    .sort((a, b) => b.priority - a.priority || String(a.created_at).localeCompare(String(b.created_at)));
  const casePage = { items: caseItems, next_cursor: null };
  const claim = { items: caseItems };
  const auditTrail = audits.map((example) => example.value);
  const actionList = actions.map((example) => example.value);

  const escalateAlert = alerts.find((example) => example.variant === "escalate") ?? alerts[0];
  const escalatedCase = cases.find((example) => example.variant === "escalated") ?? cases[0];
  const accepted = {
    alert_id: escalateAlert.value.alert_id,
    status: "accepted",
    case_id: escalatedCase.value.case_id,
  };
  const duplicate = { ...accepted, status: "duplicate" };

  useExamples(responseJson(operation("healthz"), "200"), { status: "ok", db: "ok", agent: "ok" }, [
    ["ok", { status: "ok", db: "ok", agent: "ok" }],
  ]);

  const ingest = operation("ingestSplunkAlert");
  useExamples(requestJson(ingest), webhooks[0].value, named(webhooks));
  useExamples(responseJson(ingest, "202"), accepted, [["accepted", accepted]]);
  useExamples(responseJson(ingest, "200"), duplicate, [["duplicate", duplicate]]);

  useExamples(responseJson(operation("getAlert"), "200"), alerts[0].value, named(alerts));
  useExamples(responseJson(operation("getTriageDecision"), "200"), decisions[0].value, named(decisions));
  useExamples(responseJson(operation("listCases"), "200"), casePage, [["page", casePage]]);
  useExamples(responseJson(operation("botListQueue"), "200"), casePage, [["page", casePage]]);

  for (const operationId of ["getCase", "releaseCase", "assignCase", "transitionCase"]) {
    useExamples(responseJson(operation(operationId), "200"), cases[0].value, named(cases));
  }
  useExamples(responseJson(operation("claimNext"), "200"), claim, [["claimed", claim]]);
  useExamples(responseJson(operation("botClaim"), "200"), claim, [["claimed", claim]]);

  useExamples(responseJson(operation("getEvidencePack"), "200"), evidence[0].value, named(evidence));
  useExamples(responseJson(operation("botAddEnrichment"), "201"), evidence[0].value, named(evidence));
  useExamples(responseJson(operation("getNextStepsPack"), "200"), nextSteps[0].value, named(nextSteps));
  useExamples(responseJson(operation("botPropose"), "201"), nextSteps[0].value, named(nextSteps));

  useExamples(responseJson(operation("getCaseAudit"), "200"), auditTrail, [
    ["all", auditTrail],
    ...audits.map((example) => [example.variant, [example.value]]),
  ]);

  useExamples(responseJson(operation("listActions"), "200"), actionList, [
    ["all", actionList],
    ...actions.map((example) => [example.variant, [example.value]]),
  ]);
  for (const [operationId, status] of [
    ["proposeAction", "201"],
    ["approveAction", "200"],
    ["rejectAction", "200"],
  ]) {
    useExamples(responseJson(operation(operationId), status), actions[0].value, named(actions));
  }

  const running = {
    run_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    bot_id: "grokbot-priya",
    on_behalf_of: "analyst-priya",
    routine_id: "shift-routine",
    status: "running",
    started_at: "2026-11-18T02:50:00Z",
    finished_at: null,
    cases_processed: 0,
  };
  const succeeded = {
    ...running,
    status: "succeeded",
    finished_at: "2026-11-18T03:00:00Z",
    cases_processed: 1,
    summary: "Mock run closed by the console Prism server.",
  };
  useExamples(responseJson(operation("botStartRun"), "201"), running, [["running", running]]);
  useExamples(responseJson(operation("botFinishRun"), "200"), succeeded, [["succeeded", succeeded]]);

  for (const operationId of operations.keys()) {
    if (!wired.has(operationId)) {
      throw new Error(`Prism mock has no example mapping for ${operationId}`);
    }
  }
  return spec;
}

export function writePrismSpec(dest = defaultSpecPath) {
  const yaml = dump(buildPrismSpec(), { noRefs: true, lineWidth: -1 });
  mkdirSync(path.dirname(dest), { recursive: true });
  writeFileSync(dest, yaml);
  return dest;
}

function groupExamples(examples) {
  const grouped = new Map();
  for (const example of examples) {
    const list = grouped.get(example.schema) ?? [];
    list.push(example);
    grouped.set(example.schema, list);
  }
  for (const list of grouped.values()) {
    list.sort((a, b) => {
      const ar = preferenceRank(a.variant);
      const br = preferenceRank(b.variant);
      if (ar !== br) return ar - br;
      return a.variant.localeCompare(b.variant);
    });
  }
  return grouped;
}

function preferenceRank(variant) {
  const index = PREFERRED_VARIANTS.indexOf(variant);
  return index === -1 ? PREFERRED_VARIANTS.length : index;
}

function named(examples) {
  return examples.map((example) => [example.variant, example.value]);
}

function operationsById(spec) {
  const map = new Map();
  for (const [route, item] of Object.entries(spec.paths ?? {})) {
    if (!item || typeof item !== "object") continue;
    for (const method of HTTP_METHODS) {
      const op = item[method];
      if (op?.operationId) map.set(op.operationId, op);
      else if (op) throw new Error(`${method.toUpperCase()} ${route} is missing operationId`);
    }
  }
  return map;
}

function responseJson(op, status) {
  const response = op.responses?.[status];
  if (!response || response.$ref) {
    throw new Error(`${op.operationId} is missing an inline ${status} response`);
  }
  response.content ??= {};
  response.content["application/json"] ??= {};
  return response.content["application/json"];
}

function requestJson(op) {
  const body = op.requestBody;
  if (!body || body.$ref) throw new Error(`${op.operationId} is missing an inline request body`);
  body.content ??= {};
  body.content["application/json"] ??= {};
  return body.content["application/json"];
}

function useExamples(media, preferred, variants) {
  media.example = preferred;
  media.examples = {};
  for (const [name, value] of variants) {
    media.examples[name] = { value };
  }
}

function rewriteRelativeRefs(node) {
  if (Array.isArray(node)) {
    for (const item of node) rewriteRelativeRefs(item);
    return;
  }
  if (!node || typeof node !== "object") return;
  if (typeof node.$ref === "string" && node.$ref.startsWith("./")) {
    node.$ref = `../../../contracts/${node.$ref.slice(2)}`;
  }
  for (const value of Object.values(node)) rewriteRelativeRefs(value);
}
