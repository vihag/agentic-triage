import { useQuery } from "@tanstack/react-query";
import type { ApiClient } from "./api/client";
import { fetchCases, fetchHealth } from "./api/queries";

export function App({ client }: { client: ApiClient }) {
  const health = useQuery({
    queryKey: ["healthz"],
    queryFn: () => fetchHealth(client),
  });
  const cases = useQuery({
    queryKey: ["cases"],
    queryFn: () => fetchCases(client),
  });

  return (
    <main>
      <h1>Analyst Console</h1>
      {health.isPending || cases.isPending ? <p>Loading console…</p> : null}
      {health.isError || cases.isError ? <p role="alert">API unavailable</p> : null}
      {health.data ? <p>API status: {health.data.status}</p> : null}
      {cases.data ? (
        <section>
          <h2>Cases</h2>
          <ul>
            {cases.data.items.map((item) => (
              <li key={item.case_id}>{item.title}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </main>
  );
}
