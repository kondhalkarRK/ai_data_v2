"use client";

import { ChevronLeft } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Standard back control for Semantic Atlas sub-pages (Ontology, Models, Glossary).
 * Links to the Semantic hub so deep-links and refresh still have a clear parent.
 */
export function SemanticBackLink({
  href = "/semantic",
  className,
}: {
  href?: string;
  className?: string;
}) {
  return (
    <div className={cn(className)}>
      <Button
        asChild
        variant="ghost"
        size="sm"
        className="-ml-2 h-8 gap-1 px-2 text-muted-foreground hover:text-foreground"
      >
        <Link href={href} aria-label="Back to Semantic Atlas">
          <ChevronLeft className="size-4" aria-hidden="true" />
          Back
        </Link>
      </Button>
    </div>
  );
}
