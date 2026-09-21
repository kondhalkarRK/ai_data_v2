"use client";

import Link from "next/link";

import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";

export default function SystemLogsPage() {
  return (
    <>
      <PageHeader
        title="System Logs"
        description="Admin-only operator diagnostics. Business users should use Query History and Data Trust Center instead."
      />
      <Card>
        <CardContent className="space-y-3 pt-4">
          <CardTitle className="text-sm">What this is for</CardTitle>
          <CardDescription>
            The API writes structured JSON logs (request IDs in <code>x-request-id</code>), auth
            events in <code>auth_audit_events</code>, and chat executions in{" "}
            <code>query_history</code>. This page is a checklist for operators — it is not a
            dashboard for executives or analysts.
          </CardDescription>
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            <li>
              Analysts: open{" "}
              <Link href="/query-history" className="text-primary hover:underline">
                Query History
              </Link>{" "}
              for every question, SQL, and status.
            </li>
            <li>
              Stewards: open the{" "}
              <Link href="/data-quality" className="text-primary hover:underline">
                Data Trust Center
              </Link>{" "}
              for quality incidents.
            </li>
            <li>
              Platform: see <code>docs/06-security-checklist.md</code> and{" "}
              <code>docs/07-parity-checklist.md</code>.
            </li>
          </ul>
        </CardContent>
      </Card>
    </>
  );
}
