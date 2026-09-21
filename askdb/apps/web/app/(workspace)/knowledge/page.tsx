"use client";

import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, Play, Search, Sparkles, Upload } from "lucide-react";
import Link from "next/link";

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
  deduped?: boolean;
  version?: number;
  collection?: string;
  suggestedQuestions?: string[];
}

interface Citation {
  documentId: string;
  title: string;
  chunkId: string;
  snippet: string;
  locator: string;
  untrusted: boolean;
  confidence?: number;
  collection?: string;
}

const COLLECTIONS = [
  "general",
  "dealer_reports",
  "market_research",
  "product_catalogs",
  "sales_reports",
  "policies",
] as const;

const SAMPLE_DOCS = [
  {
    title: "Dealer performance policy (sample)",
    body: "Platinum dealers must maintain NPS above 70. Revenue targets are reviewed monthly. Settlement SLAs are 7 days for standard claims.",
  },
  {
    title: "Claims settlement FAQ (sample)",
    body: "Claims settlement is the time from first notice of loss to paid or closed status. High severity claims require steward review before payout.",
  },
];

const DEMO_STEPS = [
  "1. Upload a policy, FAQ, or report (PDF, Word, or text).",
  "2. Wait until chunks appear — that means the document is searchable.",
  "3. Search here, or ask the same question in AI Chat.",
];

export default function KnowledgePage() {
  const industry = useActiveIndustry();
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("claims settlement");
  const [hits, setHits] = useState<Citation[]>([]);
  const [webRetrieval, setWebRetrieval] = useState(false);
  const [collection, setCollection] = useState<string>("general");
  const [searchCollection, setSearchCollection] = useState<string>("");
  const [guideOpen, setGuideOpen] = useState(true);
  const fileInputId = "knowledge-upload-input";

  const docs = useQuery({
    queryKey: ["documents", industry],
    queryFn: () => apiClient.get<KnowledgeDoc[]>("/api/v1/documents", { industry }),
  });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.append("file", file);
      body.append("title", file.name);
      body.append("collection", collection);
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

  const remove = useMutation({
    mutationFn: (documentId: string) =>
      apiClient.delete<{ status: string }>(`/api/v1/documents/${documentId}`, { industry }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents", industry] }),
  });

  const reindex = useMutation({
    mutationFn: () =>
      apiClient.post<{ documents?: number; chunks?: number } | Record<string, number>>(
        "/api/v1/documents/reindex",
        {},
        { industry },
      ),
  });

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    const result = await apiClient.post<Citation[]>(
      "/api/v1/documents/search",
      { query, webRetrieval, collection: searchCollection || undefined },
      { industry },
    );
    setHits(result);
  }

  function tryDemo() {
    setQuery("What is the claims settlement SLA?");
    setGuideOpen(true);
    void (async () => {
      const result = await apiClient.post<Citation[]>(
        "/api/v1/documents/search",
        { query: "claims settlement", webRetrieval: false },
        { industry },
      );
      setHits(result);
    })();
  }

  function uploadSample(sample: (typeof SAMPLE_DOCS)[number]) {
    const file = new File([sample.body], `${sample.title}.txt`, { type: "text/plain" });
    upload.mutate(file);
  }

  return (
    <>
      <PageHeader
        title="Knowledge Hub"
        description="Give AI Chat the documents behind the numbers — policies, FAQs, and research — with citations."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" size="sm" onClick={tryDemo}>
              <Play className="size-3.5" />
              Try Demo
            </Button>
            <Button type="button" size="sm" onClick={() => document.getElementById(fileInputId)?.click()}>
              <Upload className="size-3.5" />
              Upload document
            </Button>
          </div>
        }
      />

      {guideOpen ? (
        <Card className="mb-4 border-info/30 bg-info/5">
          <CardContent className="space-y-3 pt-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle className="text-sm">How Knowledge Hub works</CardTitle>
                <CardDescription className="mt-1">
                  This is not a replacement for the warehouse. It adds written context so Chat can
                  answer “why” and “what is the policy” with a citation.
                </CardDescription>
              </div>
              <Button type="button" size="sm" variant="ghost" onClick={() => setGuideOpen(false)}>
                Dismiss
              </Button>
            </div>
            <ol className="grid gap-2 text-sm sm:grid-cols-3">
              {DEMO_STEPS.map((step) => (
                <li key={step} className="rounded-xl border border-border/60 bg-background px-3 py-2">
                  {step}
                </li>
              ))}
            </ol>
            <p className="text-xs text-muted-foreground">
              Guided walkthrough: upload → chunks appear → search or{" "}
              <Link href="/chat" className="font-medium text-primary hover:underline">
                ask in AI Chat
              </Link>
              .
            </p>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <Card>
          <CardContent className="space-y-3 pt-4">
            <div className="flex items-center justify-between gap-2">
              <div>
                <CardTitle className="text-sm">Library</CardTitle>
                <CardDescription>Industry-scoped documents with chunking and citations.</CardDescription>
              </div>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                disabled={reindex.isPending}
                onClick={() => reindex.mutate()}
              >
                Reindex
              </Button>
            </div>

            <div className="rounded-2xl border border-dashed border-primary/40 bg-primary/5 p-4">
              <p className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <FileUp className="size-4" />
                Upload / ingest
              </p>
              <input
                id={fileInputId}
                type="file"
                className="sr-only"
                accept=".txt,.md,.html,.csv,.pdf,.docx"
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) upload.mutate(file);
                  event.target.value = "";
                }}
              />
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  onClick={() => document.getElementById(fileInputId)?.click()}
                  disabled={upload.isPending}
                >
                  <Upload className="size-3.5" />
                  {upload.isPending ? "Uploading…" : "Choose file"}
                </Button>
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  Collection
                  <select
                    className="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
                    value={collection}
                    onChange={(event) => setCollection(event.target.value)}
                  >
                    {COLLECTIONS.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {upload.isError ? (
                <p className="mt-2 text-xs text-danger">{(upload.error as Error).message}</p>
              ) : (
                <p className="mt-2 text-xs text-muted-foreground">
                  Text, Markdown, HTML, CSV, PDF, DOCX. This is the onboarding path: file → chunks →
                  searchable.
                </p>
              )}
            </div>

            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Sample documents
              </p>
              <div className="flex flex-wrap gap-2">
                {SAMPLE_DOCS.map((sample) => (
                  <Button
                    key={sample.title}
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={() => uploadSample(sample)}
                  >
                    <Sparkles className="size-3.5" />
                    {sample.title}
                  </Button>
                ))}
              </div>
            </div>

            {docs.isPending ? <LoadingState size="sm" title="Loading documents" /> : null}
            <ul className="space-y-2 text-sm">
              {(docs.data ?? []).map((doc) => (
                <li key={doc.id} className="rounded-md border border-border px-3 py-2">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-medium">{doc.title}</p>
                      <CardDescription>
                        {doc.collection ?? "general"} · {doc.chunkCount} chunks
                        {doc.version != null ? ` · v${doc.version}` : ""}
                        {doc.deduped ? " · deduped" : ""} · {new Date(doc.createdAt).toLocaleString()}
                      </CardDescription>
                      {doc.suggestedQuestions?.length ? (
                        <ul className="mt-1 list-disc pl-4 text-2xs text-muted-foreground">
                          {doc.suggestedQuestions.slice(0, 3).map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                    <Button type="button" size="sm" variant="ghost" onClick={() => remove.mutate(doc.id)}>
                      Delete
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-3 pt-4">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Search className="size-4" />
              Ask the library
            </CardTitle>
            <form className="space-y-2" onSubmit={onSearch}>
              <input
                className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label="Search documents"
                placeholder="e.g. claims settlement SLA"
              />
              <select
                className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
                value={searchCollection}
                onChange={(event) => setSearchCollection(event.target.value)}
              >
                <option value="">All collections</option>
                {COLLECTIONS.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
              <label className="flex items-center gap-2 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={webRetrieval}
                  onChange={(event) => setWebRetrieval(event.target.checked)}
                />
                Include opt-in web retrieval (allowlist / SSRF-safe)
              </label>
              <div className="flex flex-wrap gap-2">
                <Button type="submit" size="sm">
                  Search
                </Button>
                <Button type="button" size="sm" variant="secondary" asChild>
                  <Link href={`/chat?q=${encodeURIComponent(query)}`}>Open in AI Chat</Link>
                </Button>
              </div>
            </form>
            <ul className="space-y-2">
              {hits.map((hit) => (
                <li key={hit.chunkId} className="rounded-md border border-border px-3 py-2 text-sm">
                  <p className="font-medium">
                    {hit.title} · {hit.locator}
                    {hit.confidence != null ? ` · ${Math.round(hit.confidence * 100)}%` : ""}
                    {hit.untrusted ? " · untrusted" : ""}
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
