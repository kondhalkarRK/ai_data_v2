"use client";

import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { useActiveIndustry } from "@/hooks/use-session";
import { API_BASE_URL, apiClient } from "@/lib/api-client";

interface KnowledgeDoc {
  id: string;
  title: string;
  filename: string;
  chunkCount: number;
  createdAt: string;
}

interface Citation {
  documentId: string;
  title: string;
  chunkId: string;
  snippet: string;
  locator: string;
  untrusted: boolean;
}

export default function KnowledgePage() {
  const industry = useActiveIndustry();
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("claims settlement");
  const [hits, setHits] = useState<Citation[]>([]);

  const docs = useQuery({
    queryKey: ["documents", industry],
    queryFn: () => apiClient.get<KnowledgeDoc[]>("/api/v1/documents", { industry }),
  });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.append("file", file);
      body.append("title", file.name);
      const csrf = document.cookie.match(/(?:^|; )nql_csrf=([^;]*)/)?.[1];
      const response = await fetch(`${API_BASE_URL}/api/v1/documents`, {
        method: "POST",
        credentials: "include",
        headers: {
          "x-industry": industry,
          ...(csrf ? { "x-csrf-token": decodeURIComponent(csrf) } : {}),
        },
        body,
      });
      if (!response.ok) {
        throw new Error(`Upload failed (${response.status})`);
      }
      return (await response.json()) as KnowledgeDoc;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents", industry] }),
  });

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    const result = await apiClient.post<Citation[]>(
      "/api/v1/documents/search",
      { query },
      { industry },
    );
    setHits(result);
  }

  return (
    <>
      <PageHeader
        title="Knowledge"
        description="Industry-scoped documents with chunking, hash embeddings and cited retrieval."
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardContent className="space-y-3 pt-4">
            <CardTitle className="text-sm">Documents</CardTitle>
            <input
              type="file"
              accept=".txt,.md,.html,.csv"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) upload.mutate(file);
              }}
            />
            {docs.isPending ? <LoadingState size="sm" title="Loading documents" /> : null}
            <ul className="space-y-2 text-sm">
              {(docs.data ?? []).map((doc) => (
                <li key={doc.id} className="rounded-md border border-border px-3 py-2">
                  <p className="font-medium">{doc.title}</p>
                  <CardDescription>
                    {doc.chunkCount} chunks · {new Date(doc.createdAt).toLocaleString()}
                  </CardDescription>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-3 pt-4">
            <CardTitle className="text-sm">Retrieve</CardTitle>
            <form className="flex gap-2" onSubmit={onSearch}>
              <input
                className="h-9 flex-1 rounded-md border border-border bg-background px-3 text-sm"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
              <Button type="submit" size="sm">
                Search
              </Button>
            </form>
            <ul className="space-y-2">
              {hits.map((hit) => (
                <li key={hit.chunkId} className="rounded-md border border-border px-3 py-2 text-sm">
                  <p className="font-medium">
                    {hit.title} · {hit.locator}
                  </p>
                  <p className="text-muted-foreground">{hit.snippet}</p>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
