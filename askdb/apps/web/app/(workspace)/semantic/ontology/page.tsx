"use client";

import { ChevronLeft } from "lucide-react";
import Link from "next/link";

import { LoadingState } from "@/components/loading/loading-state";
import { OntologyBrowser } from "@/components/ontology/ontology-browser";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useOntologySnapshot } from "@/hooks/use-semantic";

export default function OntologyPage() {
  const snapshot = useOntologySnapshot();

  return (
    <>
      <div className="mb-3 flex items-center gap-3">
        <Button asChild variant="ghost" size="icon-sm">
          <Link href="/semantic" aria-label="Back to Semantic Core">
            <ChevronLeft />
          </Link>
        </Button>
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Ontology Browser</h1>
          <p className="text-xs uppercase tracking-[0.12em] text-muted-foreground">
            Semantic Core · Knowledge Graph
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
        <OntologyBrowser snapshot={snapshot.data} />
      )}
    </>
  );
}
