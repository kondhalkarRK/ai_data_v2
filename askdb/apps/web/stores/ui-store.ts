"use client";

import type { Industry } from "@nql/shared-types";
import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * Lightweight client-only UI state.
 *
 * Deliberately small: anything the server owns (the session, the user's saved default
 * industry, conversation history) lives in TanStack Query or the database, not here.
 * This holds only what would be annoying to lose on navigation.
 */
interface UiState {
  sidebarCollapsed: boolean;
  presenterMode: boolean;
  commandPaletteOpen: boolean;
  /** Overrides the user's saved default for this browser session only. */
  industryOverride: Industry | null;

  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  togglePresenterMode: () => void;
  setCommandPaletteOpen: (open: boolean) => void;
  setIndustryOverride: (industry: Industry | null) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      presenterMode: false,
      commandPaletteOpen: false,
      industryOverride: null,

      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      togglePresenterMode: () => set((state) => ({ presenterMode: !state.presenterMode })),
      setCommandPaletteOpen: (commandPaletteOpen) => set({ commandPaletteOpen }),
      setIndustryOverride: (industryOverride) => set({ industryOverride }),
    }),
    {
      name: "nql-ui",
      // The palette is transient, and the industry override should not outlive the tab.
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        presenterMode: state.presenterMode,
      }),
    },
  ),
);
