"use client";

import { Suspense } from "react";

import { ChatWorkspace } from "@/components/chat/chat-workspace";
import { LoadingState } from "@/components/loading/loading-state";

export default function ChatPage() {
  return (
    <Suspense fallback={<LoadingState title="Opening chat" size="lg" />}>
      <ChatWorkspace />
    </Suspense>
  );
}
