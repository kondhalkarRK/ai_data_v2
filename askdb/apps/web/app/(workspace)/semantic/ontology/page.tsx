"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { LoadingState } from "@/components/loading/loading-state";
import { OntologyBrowser } from "@/components/ontology/ontology-browser";
import { SemanticBackLink } from "@/components/semantic/semantic-back-link";
import { Card, CardContent } from "@/components/ui/card";
import { useOntologySnapshot } from "@/hooks/use-semantic";

export default function OntologyPage() {
  return (
    <Suspense fallback={<LoadingState title="Opening semantic graph" size="lg" />}>
      <OntologyPageInner />
    </Suspense>
  );
}

function OntologyPageInner() {
  const snapshot = useOntologySnapshot();
  const searchParams = useSearchParams();
  const focus = searchParams.get("focus");

  return (
    <>
      <div className="mb-3 flex items-center gap-3">
        <SemanticBackLink />
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Semantic Galaxy</h1>
          <p className="text-xs uppercase tracking-[0.12em] text-muted-foreground">
            Ontology · Enterprise Knowledge Graph
          </p>
        </div>
      </div>

      {snapshot.isPending ? (
        <LoadingState title="Building semantic relationships" size="lg" />
      ) : snapshot.isError ? (
        <Card>
          <CardContent className="pt-5 text-sm text-danger">
            The ontology snapshot could not be loaded. Validate the active industry pack
            and retry.
          </CardContent>
        </Card>
      ) : (
        <OntologyBrowser snapshot={snapshot.data} initialFocusId={focus} />
      )}
    </>
  );
}
