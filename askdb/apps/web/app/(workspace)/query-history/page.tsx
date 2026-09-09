"use client";

import { useQuery } from "@tanstack/react-query";

import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { useActiveIndustry } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";

interface HistoryRow {
  id: string;
  question: string;
  sqlText: string | null;
  status: string;
  rowCount: number | null;
  trustScore: number | null;
  latencyMs: number | null;
  createdAt: string;
}

export default function QueryHistoryPage() {
  const industry = useActiveIndustry();
  const history = useQuery({
    queryKey: ["history", industry],
    queryFn: () => apiClient.get<HistoryRow[]>("/api/v1/history", { industry }),
  });

  return (
    <>
      <PageHeader title="Query History" description="Executed questions with SQL, trust and latency." />
      {history.isPending ? (
        <LoadingState title="Loading history" />
      ) : (
        <div className="space-y-2">
          {(history.data ?? []).map((row) => (
            <Card key={row.id}>
              <CardContent className="pt-4">
                <CardTitle className="text-sm">{row.question}</CardTitle>
                <CardDescription>
                  {row.status} · trust {row.trustScore ?? "—"} · {row.latencyMs ?? "—"} ms ·{" "}
                  {new Date(row.createdAt).toLocaleString()}
                </CardDescription>
                {row.sqlText ? (
                  <pre className="mt-2 overflow-auto rounded bg-muted/40 p-2 font-mono text-2xs">
                    {row.sqlText}
                  </pre>
                ) : null}
              </CardContent>
            </Card>
          ))}
          {history.data?.length === 0 ? (
            <p className="text-sm text-muted-foreground">No history yet. Ask a question in AI Chat.</p>
          ) : null}
        </div>
      )}
    </>
  );
}
