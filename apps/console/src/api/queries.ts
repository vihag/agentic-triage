import type { ApiClient } from "./client";

export async function fetchHealth(client: ApiClient) {
  const { data, error, response } = await client.GET("/v1/healthz");
  if (!response.ok || !data) {
    throw new Error(`GET /v1/healthz failed (${response.status}): ${formatError(error)}`);
  }
  return data;
}

export async function fetchCases(client: ApiClient) {
  const { data, error, response } = await client.GET("/v1/cases");
  if (!response.ok || !data) {
    throw new Error(`GET /v1/cases failed (${response.status}): ${formatError(error)}`);
  }
  return data;
}

export async function fetchCase(client: ApiClient, caseId: string) {
  const { data, error, response } = await client.GET("/v1/cases/{case_id}", {
    params: { path: { case_id: caseId } },
  });
  if (!response.ok || !data) {
    throw new Error(`GET /v1/cases/${caseId} failed (${response.status}): ${formatError(error)}`);
  }
  return { case: data, etag: response.headers.get("etag") };
}

export async function fetchEvidence(client: ApiClient, caseId: string) {
  const { data, error, response } = await client.GET("/v1/cases/{case_id}/evidence", {
    params: { path: { case_id: caseId } },
  });
  if (!response.ok || !data) {
    throw new Error(`GET evidence failed (${response.status}): ${formatError(error)}`);
  }
  return data;
}

export async function fetchNextSteps(client: ApiClient, caseId: string) {
  const { data, error, response } = await client.GET("/v1/cases/{case_id}/next-steps", {
    params: { path: { case_id: caseId } },
  });
  if (!response.ok || !data) {
    throw new Error(`GET next-steps failed (${response.status}): ${formatError(error)}`);
  }
  return data;
}

export async function fetchActions(client: ApiClient, caseId: string) {
  const { data, error, response } = await client.GET("/v1/cases/{case_id}/actions", {
    params: { path: { case_id: caseId } },
  });
  if (!response.ok || !data) {
    throw new Error(`GET actions failed (${response.status}): ${formatError(error)}`);
  }
  return data;
}

export async function approveAction(client: ApiClient, caseId: string, actionId: string) {
  const { data, error, response } = await client.POST(
    "/v1/cases/{case_id}/actions/{action_id}/approve",
    { params: { path: { case_id: caseId, action_id: actionId } }, body: {} },
  );
  if (!response.ok || !data) {
    throw new Error(`approve failed (${response.status}): ${formatError(error)}`);
  }
  return data;
}

export async function rejectAction(client: ApiClient, caseId: string, actionId: string) {
  const { data, error, response } = await client.POST(
    "/v1/cases/{case_id}/actions/{action_id}/reject",
    { params: { path: { case_id: caseId, action_id: actionId } }, body: {} },
  );
  if (!response.ok || !data) {
    throw new Error(`reject failed (${response.status}): ${formatError(error)}`);
  }
  return data;
}

function formatError(error: unknown): string {
  if (error === undefined) return "empty body";
  return JSON.stringify(error);
}