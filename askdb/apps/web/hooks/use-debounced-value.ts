"use client";

import { useEffect, useState } from "react";

/** Coalesce filter changes; query keys and request aborts still protect response ordering. */
export function useDebouncedValue<T>(value: T, delay = 180): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timeout = window.setTimeout(() => setSettled(value), delay);
    return () => window.clearTimeout(timeout);
  }, [value, delay]);
  return settled;
}
