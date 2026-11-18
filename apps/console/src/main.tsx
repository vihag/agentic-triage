import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { createApiClient, DEV_API_BASE_URL, DEV_API_TOKEN } from "./api/client";
import "./index.css";

const root = document.getElementById("root");
if (!root) throw new Error("root element missing");

const queryClient = new QueryClient();
const client = createApiClient({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? DEV_API_BASE_URL,
  token: import.meta.env.VITE_API_TOKEN ?? DEV_API_TOKEN,
});

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App client={client} />
    </QueryClientProvider>
  </StrictMode>,
);
