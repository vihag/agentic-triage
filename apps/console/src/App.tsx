import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { ApiClient } from "./api/client";
import {
  approveAction,
  fetchActions,
  fetchCase,
  fetchCases,
  fetchEvidence,
  fetchHealth,
  fetchNextSteps,
  rejectAction,
} from "./api/queries";

export function App({ client }: { client: ApiClient }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const health = useQuery({
    queryKey: ["healthz"],
    queryFn: () => fetchHealth(client),
  });
  const cases = useQuery({
    queryKey: ["cases"],
    queryFn: () => fetchCases(client),
  });
  const detail = useQuery({
    queryKey: ["case", selectedId],
    queryFn: () => fetchCase(client, selectedId!),
    enabled: selectedId !== null,
  });
  const evidence = useQuery({
    queryKey: ["evidence", selectedId],
    queryFn: () => fetchEvidence(client, selectedId!),
    enabled: selectedId !== null,
  });
  const nextSteps = useQuery({
    queryKey: ["nextSteps", selectedId],
    queryFn: () => fetchNextSteps(client, selectedId!),
    enabled: selectedId !== null,
  });
  const actions = useQuery({
    queryKey: ["actions", selectedId],
    queryFn: () => fetchActions(client, selectedId!),
    enabled: selectedId !== null,
  });

  const approve = useMutation({
    mutationFn: (actionId: string) => approveAction(client, selectedId!, actionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["actions", selectedId] });
      await queryClient.invalidateQueries({ queryKey: ["case", selectedId] });
    },
  });
  const reject = useMutation({
    mutationFn: (actionId: string) => rejectAction(client, selectedId!, actionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["actions", selectedId] });
      await queryClient.invalidateQueries({ queryKey: ["case", selectedId] });
    },
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
              <li key={item.case_id}>
                <button type="button" onClick={() => setSelectedId(item.case_id)}>
                  {item.title}
                </button>
                <span>
                  {" "}
                  — {item.status} ({item.severity})
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {selectedId && detail.data ? (
        <section>
          <h2>{detail.data.case.title}</h2>
          <p>
            Status: {detail.data.case.status} · Pending actions:{" "}
            {detail.data.case.pending_action_count ?? 0}
          </p>
          {evidence.data ? (
            <section>
              <h3>Evidence</h3>
              <p>{evidence.data.summary}</p>
            </section>
          ) : null}
          {nextSteps.data ? (
            <section>
              <h3>Next steps</h3>
              <ol>
                {nextSteps.data.steps.map((step) => (
                  <li key={step.step_id}>{step.title}</li>
                ))}
              </ol>
            </section>
          ) : null}
          {actions.data ? (
            <section>
              <h3>Actions</h3>
              <ul>
                {actions.data.map((action) => (
                  <li key={action.action_id}>
                    {action.type} — {action.status}
                    {action.status === "proposed" ? (
                      <>
                        {" "}
                        <button
                          type="button"
                          onClick={() => approve.mutate(action.action_id)}
                          disabled={approve.isPending}
                        >
                          Approve
                        </button>{" "}
                        <button
                          type="button"
                          onClick={() => reject.mutate(action.action_id)}
                          disabled={reject.isPending}
                        >
                          Reject
                        </button>
                      </>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}