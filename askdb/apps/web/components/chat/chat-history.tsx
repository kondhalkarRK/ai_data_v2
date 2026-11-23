"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { History, X } from "lucide-react";
import { useState } from "react";

import { useChatSession } from "@/hooks/use-chat-ask";
import { apiClient } from "@/lib/api-client";
import { Button } from "@/components/ui/button";

export function ChatHistory() {
  const [open, setOpen] = useState(false);
  const chat = useChatSession();
  const history = useQuery({
    queryKey: ["chat-conversations", chat.user?.id, chat.industry],
    queryFn: () => apiClient.get<{ items: Array<{ id: string; title: string; updatedAt: string }>; hasMore: boolean }>("/api/v1/chat/conversations", { industry: chat.industry }),
    enabled: open && Boolean(chat.user), staleTime: 0,
  });
  return <Dialog.Root open={open} onOpenChange={setOpen}>
    <Dialog.Trigger asChild><Button variant="ghost" size="sm" className="gap-2" aria-label="Chat history"><History className="size-4" /><span className="hidden sm:inline">History</span></Button></Dialog.Trigger>
    <Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-[80] bg-black/20" /><Dialog.Content className="fixed inset-y-0 right-0 z-[81] flex w-full max-w-sm flex-col border-l border-border bg-surface-raised p-5 shadow-overlay focus:outline-none">
      <Dialog.Title className="font-semibold">Chat history</Dialog.Title><Dialog.Description className="mt-1 text-xs text-muted-foreground">Your conversations in {chat.industry}. Opening history keeps your draft.</Dialog.Description>
      <Dialog.Close asChild><button type="button" className="icon-btn-ghost absolute right-3 top-3" aria-label="Close chat history"><X className="size-4" /></button></Dialog.Close>
      <div className="mt-5 min-h-0 flex-1 overflow-y-auto">
        {history.isPending && <p role="status" className="text-sm">Loading conversations…</p>}
        {history.isError && <div role="alert" className="text-sm"><p>Could not load conversations.</p><button type="button" className="mt-2 underline" onClick={() => void history.refetch()}>Retry</button></div>}
        {history.data?.items.length === 0 && <p className="text-sm text-muted-foreground">Your conversations will appear here.</p>}
        <ul className="space-y-1">{history.data?.items.map(item => <li key={item.id}><button type="button" aria-current={item.id === chat.conversationId ? "true" : undefined} disabled={chat.busy || chat.restoring} className="w-full rounded-xl p-3 text-left text-sm hover:bg-muted aria-[current=true]:bg-primary/10 disabled:opacity-50" onClick={() => { void chat.openConversation(item.id); setOpen(false); }}><span className="block truncate font-medium">{item.title}</span><time dateTime={item.updatedAt} className="mt-1 block text-xs text-muted-foreground">{new Date(item.updatedAt).toLocaleDateString()}</time></button></li>)}</ul>
        {history.data?.hasMore && <p className="mt-4 text-xs text-muted-foreground">Showing the 200 most recently updated conversations.</p>}
      </div>
    </Dialog.Content></Dialog.Portal>
  </Dialog.Root>;
}
