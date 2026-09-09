"use client";

import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { useActiveIndustry } from "@/hooks/use-session";
import { apiClient } from "@/lib/api-client";

interface SavedRow {
  id: string;
  title: string;
  question: string;
  sqlText: string | null;
  createdAt: string;
}

export default function SavedQuestionsPage() {
  const industry = useActiveIndustry();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [question, setQuestion] = useState("");

  const saved = useQuery({
    queryKey: ["saved-questions", industry],
    queryFn: () => apiClient.get<SavedRow[]>("/api/v1/questions", { industry }),
  });

  const create = useMutation({
    mutationFn: () =>
      apiClient.post("/api/v1/questions", { title, question }, { industry }),
    onSuccess: async () => {
      setTitle("");
      setQuestion("");
      await queryClient.invalidateQueries({ queryKey: ["saved-questions", industry] });
    },
  });

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (title && question) create.mutate();
  }

  return (
    <>
      <PageHeader title="Saved Questions" description="Personal governed question collection." />
      <Card className="mb-4">
        <CardContent className="pt-4">
          <form className="grid gap-2 md:grid-cols-[1fr_2fr_auto]" onSubmit={onSubmit}>
            <input
              className="h-9 rounded-md border border-border bg-background px-3 text-sm"
              placeholder="Title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
            <input
              className="h-9 rounded-md border border-border bg-background px-3 text-sm"
              placeholder="Question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
            />
            <Button type="submit" size="sm">
              Save
            </Button>
          </form>
        </CardContent>
      </Card>
      {saved.isPending ? (
        <LoadingState title="Loading saved questions" />
      ) : (
        <div className="space-y-2">
          {(saved.data ?? []).map((row) => (
            <Card key={row.id}>
              <CardContent className="pt-4">
                <CardTitle className="text-sm">{row.title}</CardTitle>
                <CardDescription>{row.question}</CardDescription>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
