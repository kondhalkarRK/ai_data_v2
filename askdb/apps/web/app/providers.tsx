"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import * as React from "react";

import { ApiError } from "@/lib/api-client";

function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Semantic snapshots and metadata change rarely; a minute of staleness removes
        // most refetching without making the UI feel out of date.
        staleTime: 60_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          // Retrying a 401, 403 or 422 just repeats the same failure.
          if (error instanceof ApiError) {
            return error.isRetryable && failureCount < 2;
          }
          return failureCount < 2;
        },
        retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export function Providers({ children }: { children: React.ReactNode }) {
  // useState rather than a module singleton: in the App Router a shared client would
  // leak cached data between users during server rendering.
  const [queryClient] = React.useState(createQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider
        attribute="class"
        // Light is the default per spec section 9; dark is fully supported.
        defaultTheme="light"
        enableSystem
        // Transitions on a theme swap cause a visible repaint; disabling them is what
        // keeps the toggle inside the 50 ms budget.
        disableTransitionOnChange
        storageKey="nql-theme"
      >
        {children}
      </ThemeProvider>
    </QueryClientProvider>
  );
}
