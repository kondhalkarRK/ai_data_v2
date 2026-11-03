"use client";

import { Activity, Bot, Database, DatabaseZap, Gauge, ScrollText, ShieldCheck } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import {
  AiGovernancePanel,
  AuditCenterPanel,
  GovernanceDashboardPanel,
  LlmUsagePanel,
  SemanticAdminPanel,
  TrustAdminPanel,
} from "@/components/admin/admin-panels";
import { EntityCatalogAdminPanel } from "@/components/admin/entity-catalog-admin";
import { ChatQuotaWidget } from "@/components/governance/chat-quota-widget";
import { PageHeader } from "@/components/shell/page-header";
import { PageShell } from "@/components/ui/page-shell";
import { EmptyState } from "@/components/ui/status-pill";
import { useSession } from "@/hooks/use-session";
import { cn } from "@/lib/utils";

const TABS = [
  { id: "ai", label: "LLM Settings", icon: Bot, panel: AiGovernancePanel },
  { id: "governance", label: "Hybrid AI Dashboard", icon: Activity, panel: GovernanceDashboardPanel },
  { id: "usage", label: "LLM Usage", icon: Gauge, panel: LlmUsagePanel },
  { id: "trust", label: "Data Trust Admin", icon: ShieldCheck, panel: TrustAdminPanel },
  { id: "semantic", label: "Semantic Admin", icon: Database, panel: SemanticAdminPanel },
  { id: "catalog", label: "Entity Catalog (Admin)", icon: DatabaseZap, panel: EntityCatalogAdminPanel },
  { id: "audit", label: "Audit Center", icon: ScrollText, panel: AuditCenterPanel },
] as const;

type TabId = (typeof TABS)[number]["id"];

function AdminCenter() {
  const { data: user } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const requested = params.get("tab");
  const active: TabId = TABS.some((tab) => tab.id === requested) ? (requested as TabId) : "ai";
  const Panel = TABS.find((tab) => tab.id === active)!.panel;

  if (user?.role !== "admin") {
    return (
      <EmptyState
        title="Administrator access required"
        detail="The Admin Center is available to administrators only."
      />
    );
  }

  return (
    <>
      <div
        role="tablist"
        aria-label="Admin Center sections"
        className="mb-6 flex flex-wrap gap-1 rounded-[var(--radius-card)] border border-border/60 bg-muted/40 p-1"
      >
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const selected = tab.id === active;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => router.replace(`${pathname}?tab=${tab.id}`, { scroll: false })}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-[calc(var(--radius-control)-2px)] px-3 py-2 text-sm transition-[color,background-color,box-shadow] duration-150",
                selected
                  ? "bg-background font-medium text-foreground shadow-[var(--shadow-card)]"
                  : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
              )}
            >
              <Icon className="size-4" aria-hidden="true" />
              {tab.label}
            </button>
          );
        })}
      </div>
      <div role="tabpanel">
        <Panel />
      </div>
    </>
  );
}

export default function AdminPage() {
  return (
    <PageShell>
      <PageHeader
        title="Admin Center"
        description="Govern the AI: model settings, how questions are answered, who uses what, and every admin action."
        actions={<ChatQuotaWidget />}
      />
      <React.Suspense fallback={null}>
        <AdminCenter />
      </React.Suspense>
    </PageShell>
  );
}
