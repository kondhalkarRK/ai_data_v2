"use client";

import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";

export default function SystemLogsPage() {
  return (
    <>
      <PageHeader
        title="System Logs"
        description="Structured application logs are emitted by the API process; this view summarises the hardening checklist."
      />
      <Card>
        <CardContent className="space-y-2 pt-4">
          <CardTitle className="text-sm">Observability</CardTitle>
          <CardDescription>
            Request IDs appear in `x-request-id` and structured JSON logs. Auth events are stored in
            `auth_audit_events`. Chat executions land in `query_history`. See
            `docs/06-security-checklist.md` and `docs/07-parity-checklist.md`.
          </CardDescription>
        </CardContent>
      </Card>
    </>
  );
}
