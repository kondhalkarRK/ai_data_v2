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
  llmModel: string | null;
  llmTemperature: number;
  llmTopP: number;
  llmTopK: number;

  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  togglePresenterMode: () => void;
  setCommandPaletteOpen: (open: boolean) => void;
  setIndustryOverride: (industry: Industry | null) => void;
  setLlmModel: (model: string | null) => void;
  setLlmTemperature: (value: number) => void;
  setLlmTopP: (value: number) => void;
  setLlmTopK: (value: number) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      presenterMode: false,
      commandPaletteOpen: false,
      industryOverride: null,
      llmModel: null,
      llmTemperature: 0.2,
      llmTopP: 1,
      llmTopK: 40,

      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      togglePresenterMode: () => set((state) => ({ presenterMode: !state.presenterMode })),
      setCommandPaletteOpen: (commandPaletteOpen) => set({ commandPaletteOpen }),
      setIndustryOverride: (industryOverride) => set({ industryOverride }),
      setLlmModel: (llmModel) => set({ llmModel }),
      setLlmTemperature: (llmTemperature) => set({ llmTemperature }),
      setLlmTopP: (llmTopP) => set({ llmTopP }),
      setLlmTopK: (llmTopK) => set({ llmTopK }),
    }),
    {
      name: "nql-ui",
      // The palette is transient, and the industry override should not outlive the tab.
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        presenterMode: state.presenterMode,
        llmModel: state.llmModel,
        llmTemperature: state.llmTemperature,
        llmTopP: state.llmTopP,
        llmTopK: state.llmTopK,
      }),
    },
  ),
);
