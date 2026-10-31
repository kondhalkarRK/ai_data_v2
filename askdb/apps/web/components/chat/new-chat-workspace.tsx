"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";

import type { ActionKey } from "@/components/chat/action-toolbar";
import { CompactDataAnswer } from "@/components/chat/compact-data-answer";
import { ResponseCard } from "@/components/chat/response-card";
import { SuggestedQuestions } from "@/components/chat/suggested-questions";
import type { ChatMessage } from "@/components/chat/types";
import { ChatQuotaWidget } from "@/components/governance/chat-quota-widget";
import { Button } from "@/components/ui/button";
import { useChatAsk } from "@/hooks/use-chat-ask";
import { assistantView, detectAnalysisRequest } from "@/lib/chat-new-ui";

const STARTERS: Record<string, string[]> = {
  insurance: ["Premium by month", "Claims by region", "Loss ratio by product"],
  automotive: ["Revenue by month", "Top models by units sold", "Units sold by region"],
};

/** Conversational view over the same chat API as Classic. */
export function NewChatWorkspace() {
  const { industry, messages, busy, toast, runAsk, cancelInFlight, handleAction } = useChatAsk();
  const [question, setQuestion] = useState("");
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = scrollerRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [messages, busy]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const text = question;
    setQuestion("");
    await runAsk(text);
  }

  const starters = STARTERS[industry] ?? STARTERS.automotive!;

  return (
    <div className="flex h-[calc(100dvh-var(--topbar-height)-2rem)] min-h-[420px] flex-col lg:h-[calc(100dvh-var(--topbar-height)-3rem)]">
      <div className="flex shrink-0 justify-end pb-2">
        <ChatQuotaWidget />
      </div>

      <div ref={scrollerRef} className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-2 pb-6">
          {messages.length === 0 ? (
            <div className="space-y-4 py-16 text-center">
              <h1 className="text-2xl font-semibold tracking-tight">Ask Me</h1>
              <p className="text-sm text-muted-foreground">
                Ask about your business data. You get a short answer first, and can open the full
                analysis when you want it.
              </p>
              <SuggestedQuestions
                items={starters}
                disabled={busy}
                onSelect={(text) => void runAsk(text)}
                className="flex flex-col items-center"
              />
            </div>
          ) : null}

          {messages.map((message, index) =>
            message.role === "user" ? (
              <div
                key={message.id}
                className="ml-auto max-w-[85%] rounded-[var(--radius-card)] bg-primary px-4 py-2.5 text-sm text-primary-foreground"
              >
                {message.question}
              </div>
            ) : (
              <AssistantMessage
                key={message.id}
                message={message}
                question={messages[index - 1]?.question ?? ""}
                retryQuestion={messages[index - 1]?.question}
                busy={busy}
                onAsk={(text) => void runAsk(text)}
                onAction={(key, msg) => void handleAction(key, msg)}
              />
            ),
          )}
        </div>
      </div>

      <form
        className="mx-auto w-full max-w-3xl shrink-0 border-t border-border/60 bg-background/95 px-2 py-3 backdrop-blur"
        onSubmit={onSubmit}
      >
        <div className="flex gap-2">
          <input
            aria-label="Ask a question"
            className="h-11 flex-1 rounded-[var(--radius-control)] border border-border bg-background px-3 text-sm outline-none ring-primary/20 focus:ring-2"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask about your data"
          />
          {busy ? (
            <Button type="button" variant="secondary" onClick={() => void cancelInFlight()}>
              Cancel
            </Button>
          ) : (
            <Button type="submit" className="px-5">
              Ask
            </Button>
          )}
        </div>
      </form>

      {toast ? (
        <p className="fixed bottom-4 right-4 z-40 rounded-lg border border-border bg-background px-3 py-2 text-xs shadow-[var(--shadow-raised)]">
          {toast}
        </p>
      ) : null}
    </div>
  );
}

function AssistantMessage({
  message,
  question,
  retryQuestion,
  busy,
  onAsk,
  onAction,
}: {
  message: ChatMessage;
  question: string;
  retryQuestion?: string;
  busy: boolean;
  onAsk: (text: string) => void;
  onAction: (key: ActionKey, message: ChatMessage) => void;
}) {
  const view = assistantView(message);

  if (view === "data") {
    return (
      <CompactDataAnswer
        message={message}
        requestedTab={detectAnalysisRequest(question)}
        busy={busy}
        onAsk={onAsk}
        onAction={onAction}
      />
    );
  }

  if (view === "text") {
    return (
      <div className="space-y-3" data-testid="text-answer">
        <p className="max-w-[85%] whitespace-pre-wrap text-sm leading-relaxed text-foreground">
          {message.narrative || "…"}
        </p>
        {message.followups?.length ? (
          <SuggestedQuestions items={message.followups} disabled={busy} onSelect={onAsk} />
        ) : null}
      </div>
    );
  }

  return (
    <ResponseCard
      message={message}
      busy={busy}
      onAsk={onAsk}
      onRetry={retryQuestion ? () => onAsk(retryQuestion) : undefined}
      onAction={onAction}
    />
  );
}
