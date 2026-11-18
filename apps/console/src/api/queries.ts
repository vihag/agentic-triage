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

function formatError(error: unknown): string {
  if (error === undefined) return "empty body";
  return JSON.stringify(error);
}
