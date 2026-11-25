"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Info, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { useId, useState } from "react";

import type { ChatMessage, ResponseRating } from "./types";
import { SQLViewer } from "./sql-viewer";
import { AnswerProvenance, QueryPlanNote } from "./response-card";
import { TrustIndicators } from "./trust-indicators";
import { useActiveIndustry, useSession } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";
import { Button } from "@/components/ui/button";

const REASONS = [
  ["incorrect", "Incorrect answer"], ["misunderstood", "Misunderstood my question"],
  ["incomplete", "Incomplete answer"], ["unclear", "Hard to understand"], ["other", "Other"],
] as const;
type SavedRating = { feedback: ResponseRating | null };

export function ResponseActions({ message, onAsk, busy }: { message: ChatMessage; onAsk?: (question: string) => void; busy?: boolean }) {
  const industry = useActiveIndustry();
  const { data: user } = useSession();
  const client = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [reason, setReason] = useState<ResponseRating["reason"]>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const formId = useId();
  const id = message.historyId;
  const eligible = Boolean(user && id && message.complete && !message.ratingDisabled);
  const path = `/api/v1/chat/responses/${id}/rating`;
  const key = ["chat-rating", user?.id, industry, JSON.stringify(user?.regionAccess), id];
  const feedback = useQuery<SavedRating>({
    queryKey: key, queryFn: () => apiClient.get(path, { industry }), enabled: eligible,
    initialData: message.rating !== undefined ? { feedback: message.rating } : undefined,
    staleTime: 30_000, retry: false,
  });
  const mutation = useMutation({
    mutationFn: (value: ResponseRating | null) => value
      ? apiClient.put<SavedRating>(path, value, { industry })
      : apiClient.delete<SavedRating>(path, { industry }),
    onMutate: async value => {
      setError("");
      await client.cancelQueries({ queryKey: key });
      const previous = client.getQueryData<SavedRating>(key);
      client.setQueryData(key, { feedback: value });
      return { previous };
    },
    onError: (_error, _value, context) => {
      client.setQueryData(key, context?.previous ?? { feedback: null });
      setError("Your rating could not be saved. Please try again.");
    },
    onSuccess: data => { client.setQueryData(key, data); setFormOpen(false); },
  });
  const hasDetails = Boolean(message.complete && (message.meta || message.sql));
  if (!eligible && !hasDetails) return null;
  const rating = feedback.data?.feedback;
  const disabled = mutation.isPending || feedback.isPending || feedback.isError;
  return <div className="space-y-2">
    <div className="flex items-center gap-1 text-muted-foreground" aria-label="Response actions">
      <Dialog.Root>
        <Dialog.Trigger asChild><button type="button" className="icon-btn-ghost" aria-label="How Scio handled this"><Info className="size-4" /></button></Dialog.Trigger>
        <Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-[80] bg-black/30" /><Dialog.Content className="fixed left-1/2 top-1/2 z-[81] max-h-[85dvh] w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-2xl border border-border bg-surface-raised p-5 shadow-overlay">
          <Dialog.Title className="font-semibold">How Scio handled this</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-muted-foreground">Sources, interpretation and query details for this response.</Dialog.Description>
          <dl className="my-4 space-y-2 break-words text-xs"><div><dt>Source</dt><dd>{message.route ?? message.meta?.route ?? (message.sql ? "Business data" : "Conversation")}</dd></div>{id && <div><dt>Response ID</dt><dd>{id}</dd></div>}</dl>
          {message.meta && <div className="mb-4 space-y-4">
            <AnswerProvenance meta={message.meta} />
            {message.meta.confidence?.reasons.length ? <ul className="list-inside list-disc text-xs text-muted-foreground">{message.meta.confidence.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul> : null}
            <TrustIndicators groundedOn={message.meta.groundedOn ?? []} ambiguityFlag={Boolean(message.meta.ambiguityFlag)} alternates={message.meta.alternateInterpretations} onClarify={onAsk} />
            {message.meta.queryPlan && <QueryPlanNote plan={message.meta.queryPlan} />}
            {!message.meta.ambiguityFlag && message.meta.alternateInterpretations?.length ? <div className="flex flex-wrap gap-2 text-xs"><span>Did you mean:</span>{message.meta.alternateInterpretations.map(item => <button key={item} type="button" disabled={busy || !onAsk} onClick={() => onAsk?.(item)} className="rounded-full border border-border px-2 py-1 hover:bg-muted disabled:opacity-50">{item}</button>)}</div> : null}
          </div>}
          {message.sql && <details><summary className="cursor-pointer text-sm font-medium">View SQL</summary><SQLViewer sql={message.sql} queryMeta={message.meta?.queryMeta} executionTimeMs={message.meta?.executionTimeMs} rowCount={message.meta?.rowCount} sourceDatabase={message.meta?.sourceDatabase} diff={message.sqlDiff} /></details>}
          <Dialog.Close asChild><button type="button" aria-label="Close response details" className="icon-btn-ghost absolute right-3 top-3"><X className="size-4" /></button></Dialog.Close>
        </Dialog.Content></Dialog.Portal>
      </Dialog.Root>
      {eligible && <>
      <button type="button" className="icon-btn-ghost" aria-label="Thumbs up" aria-pressed={rating?.rating === "up"} disabled={disabled} onClick={() => mutation.mutate(rating?.rating === "up" ? null : { rating: "up", reason: null, note: null })}><ThumbsUp className="size-4" /></button>
      <Dialog.Root open={formOpen} onOpenChange={setFormOpen}>
        <Dialog.Trigger asChild><button type="button" className="icon-btn-ghost" aria-label="Thumbs down" aria-pressed={rating?.rating === "down"} disabled={disabled} onClick={() => { setReason(rating?.reason ?? null); setNote(rating?.note ?? ""); setError(""); }}><ThumbsDown className="size-4" /></button></Dialog.Trigger>
        <Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-[80] bg-black/30" /><Dialog.Content className="fixed left-1/2 top-1/2 z-[81] max-h-[90dvh] w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-2xl border border-border bg-surface-raised p-5 shadow-overlay">
          <Dialog.Title className="font-semibold">Help improve this answer</Dialog.Title><Dialog.Description className="mt-1 text-sm text-muted-foreground">Reason and notes are optional. Avoid including sensitive information.</Dialog.Description>
          <form className="mt-5 space-y-4" onSubmit={event => { event.preventDefault(); mutation.mutate({ rating: "down", reason, note: note.trim() || null }); }}>
            <div><label htmlFor={`${formId}-reason`} className="text-sm">Reason (optional)</label><select id={`${formId}-reason`} className="mt-1 w-full rounded-lg border border-input bg-background p-2 text-sm" value={reason ?? ""} onChange={event => setReason(event.target.value as ResponseRating["reason"] || null)}><option value="">Select a reason</option>{REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
            <div><label htmlFor={`${formId}-note`} className="text-sm">Notes (optional)</label><textarea id={`${formId}-note`} value={note} maxLength={2000} rows={3} className="mt-1 w-full rounded-lg border border-input bg-background p-2 text-sm" onChange={event => setNote(event.target.value)} /></div>
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <div className="flex flex-wrap gap-2"><Button type="submit" disabled={mutation.isPending}>Save feedback</Button>{rating && <Button type="button" variant="secondary" disabled={mutation.isPending} onClick={() => mutation.mutate(null)}>Remove rating</Button>}</div>
          </form>
          <Dialog.Close asChild><button type="button" aria-label="Close feedback" className="icon-btn-ghost absolute right-3 top-3"><X className="size-4" /></button></Dialog.Close>
        </Dialog.Content></Dialog.Portal>
      </Dialog.Root>
      </>}
      {eligible && rating && <span role="status" className="ml-2 text-[11px]">{mutation.isPending ? "Saving…" : "Feedback saved"}</span>}
    </div>
    {!formOpen && error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    {eligible && feedback.isError && <button type="button" className="text-xs underline" onClick={() => void feedback.refetch()}>Could not load feedback. Retry</button>}
  </div>;
}
