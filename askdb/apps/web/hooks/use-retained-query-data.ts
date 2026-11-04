"use client";

import { useEffect, useState } from "react";

/** Keep a successful view on refetch failure, never across an industry boundary. */
export function useRetainedQueryData<T>(data: T | undefined, industry: string): T | undefined {
  const [last, setLast] = useState<{ industry: string; data: T } | null>(null);
  useEffect(() => {
    let cancelled = false;
    if (data !== undefined) queueMicrotask(() => { if (!cancelled) setLast({ industry, data }); });
    return () => { cancelled = true; };
  }, [data, industry]);
  return data ?? (last?.industry === industry ? last.data : undefined);
}
