"use client";

import { Suspense } from "react";

import { ChatModeShell } from "@/components/chat/chat-mode-shell";
import { LoadingState } from "@/components/loading/loading-state";

export default function ChatPage() {
  return (
    <Suspense fallback={<LoadingState title="Opening chat" size="lg" />}>
      <ChatModeShell />
    </Suspense>
  );
}
