"use client";

import { AnalyticsBuilderShell } from "@/components/analytics-builder/analytics-builder-shell";
import { LoadingState } from "@/components/loading/loading-state";
import { PageHeader } from "@/components/shell/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { useSemanticPack } from "@/hooks/use-semantic";

export default function AnalyticsBuilderPage() {
  const pack = useSemanticPack();

  return (
    <>
      <PageHeader
        title="Analytics Builder"
        description="No-code business analytics powered by the semantic layer, glossary, ontology, and value dictionary."
      />
      {pack.isPending ? (
        <LoadingState title="Loading semantic catalog" size="lg" />
      ) : pack.isError ? (
        <Card>
          <CardContent className="pt-5 text-sm text-danger">
            The semantic pack could not be loaded. Confirm the active industry and try again.
          </CardContent>
        </Card>
      ) : (
        <AnalyticsBuilderShell pack={pack.data} />
      )}
    </>
  );
}
