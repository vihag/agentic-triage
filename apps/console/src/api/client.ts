import createClient, { type Client } from "openapi-fetch";
import type { paths } from "./schema";

export type ApiClient = Client<paths>;

export interface ApiClientOptions {
  baseUrl: string;
  token?: string;
  splunkToken?: string;
  headers?: HeadersInit;
}

export const DEV_API_BASE_URL = "http://127.0.0.1:4010";
export const DEV_API_TOKEN = "dev-analyst";

export function createApiClient(options: ApiClientOptions): ApiClient {
  const headers = new Headers(options.headers);
  if (options.token) headers.set("Authorization", `Bearer ${options.token}`);
  const client = createClient<paths>({
    baseUrl: options.baseUrl.replace(/\/$/u, ""),
    headers,
  });
  if (options.splunkToken) {
    const splunkToken = options.splunkToken;
    client.use({
      onRequest({ request, schemaPath }) {
        if (!schemaPath.startsWith("/v1/ingest/")) return undefined;
        const url = new URL(request.url);
        url.searchParams.set("token", splunkToken);
        const method = request.method;
        const hasBody = method !== "GET" && method !== "HEAD";
        const init: RequestInit & { duplex?: "half" } = {
          method,
          headers: request.headers,
          body: hasBody ? request.body : undefined,
        };
        if (hasBody) init.duplex = "half";
        return new Request(url, init);
      },
    });
  }
  return client;
}
