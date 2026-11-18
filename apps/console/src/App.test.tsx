import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { App } from "./App";
import { createApiClient } from "./api/client";
import { cases } from "./api/contract-examples";
import { mockBaseUrl } from "./test/mock-base-url";

test("console shell renders cases served by the Prism mock", async () => {
  const client = createApiClient({ baseUrl: mockBaseUrl(), token: "dev-analyst" });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <App client={client} />
    </QueryClientProvider>,
  );

  expect(await screen.findByRole("heading", { name: "Analyst Console" })).toBeInTheDocument();
  expect(await screen.findByText("API status: ok")).toBeInTheDocument();
  expect(await screen.findByText(cases.escalated.title)).toBeInTheDocument();
  expect(screen.getByText(cases.autoClosed.title)).toBeInTheDocument();
});

test("console shell reports when the API is unreachable", async () => {
  const client = createApiClient({ baseUrl: "http://127.0.0.1:1" });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <App client={client} />
    </QueryClientProvider>,
  );

  expect(await screen.findByRole("alert")).toHaveTextContent("API unavailable");
});
