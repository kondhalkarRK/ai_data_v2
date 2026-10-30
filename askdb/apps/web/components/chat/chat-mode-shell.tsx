"use client";

import { useState, useSyncExternalStore } from "react";

import { ChatWorkspace } from "@/components/chat/chat-workspace";
import { NewChatWorkspace } from "@/components/chat/new-chat-workspace";
import {
  CHAT_MODE_STORAGE_KEY,
  type ChatMode,
  NEW_CHAT_UI_ENABLED,
  readStoredChatMode,
} from "@/lib/chat-new-ui";
import { cn } from "@/lib/utils";

const subscribeNever = () => () => {};

const OPTIONS: Array<{ value: ChatMode; label: string }> = [
  { value: "classic", label: "Classic" },
  { value: "new", label: "New" },
];

/**
 * Flag off: exactly the Classic workspace. Flag on: a Classic | New toggle (remembered in
 * localStorage) over the same route. The toggle is absolutely positioned so Classic's layout
 * is unchanged.
 */
export function ChatModeShell({ enabled = NEW_CHAT_UI_ENABLED }: { enabled?: boolean }) {
  // null on the server and first client render, then the stored choice (no hydration mismatch,
  // and Classic never mounts first and fires a ?q= deep link when New was the saved mode).
  const stored = useSyncExternalStore<ChatMode | null>(
    subscribeNever,
    () => readStoredChatMode(window.localStorage),
    () => null,
  );
  const [chosen, setChosen] = useState<ChatMode | null>(null);
  const mode = chosen ?? stored;

  if (!enabled) return <ChatWorkspace />;
  if (!mode) return null;

  function choose(next: ChatMode) {
    setChosen(next);
    try {
      window.localStorage.setItem(CHAT_MODE_STORAGE_KEY, next);
    } catch {
      // Storage unavailable: the choice just won't persist.
    }
  }

  return (
    <div className="relative">
      <div
        role="group"
        aria-label="Chat experience"
        className="absolute left-1/2 top-0 z-10 flex -translate-x-1/2 rounded-full border border-border/70 bg-background p-0.5 text-xs shadow-sm"
      >
        {OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            aria-pressed={mode === option.value}
            onClick={() => choose(option.value)}
            className={cn(
              "rounded-full px-3 py-1 font-medium transition-colors",
              mode === option.value
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
      {mode === "new" ? <NewChatWorkspace /> : <ChatWorkspace />}
    </div>
  );
}
