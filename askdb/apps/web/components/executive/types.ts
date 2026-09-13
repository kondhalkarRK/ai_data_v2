import type { Industry } from "@nql/shared-types";

export interface ExecKpiCard {
  id: string;
  label: string;
  value: number | null;
  formatted: string;
  format: string;
  formula?: string;
  delta?: number | null;
}

export interface HealthComponent {
  kpiId: string;
  label: string;
  value: number | null;
  formatted: string;
  weight: number;
  contribution: number;
  direction: "higher_better" | "lower_better";
}

export interface BusinessHealth {
  score: number | null;
  label: string;
  components: HealthComponent[];
  formulaNote: string;
  available: boolean;
  unavailableReason?: string | null;
}

export interface AiInsight {
  id: string;
  category: "risk" | "opportunity" | "insight" | "recommendation";
  title: string;
  body: string;
  groundedOn: string[];
  metricIds: string[];
  exploreFocus: string[];
}

export interface DataQualityNotice {
  healthyPct: number | null;
  label: string;
  notices: string[];
  affectedKpiIds: string[];
}

export interface WhatIfPreset {
  id: string;
  label: string;
  metric: string;
  changeValue: number;
  direction: "up" | "down";
  supported: boolean;
  unsupportedReason?: string | null;
}

export interface SuggestedQuestion {
  id: string;
  text: string;
  supported: boolean;
}

export interface ExecutiveIntelligence {
  industry: Industry | string;
  title: string;
  tagline: string;
  window: string;
  windowLabel: string;
  compareLabel: string;
  startDate: string | null;
  endDate: string | null;
  dataAsOf: string;
  computedAt: string;
  cacheTtlSeconds: number;
  cards: ExecKpiCard[];
  series: Array<{ period: string; values: Record<string, number | null> }>;
  breakdowns: Record<string, Array<{ name: string; value: number; formatted: string }>>;
  health: BusinessHealth;
  insights: AiInsight[];
  dataQuality: DataQualityNotice;
  suggestedQuestions: SuggestedQuestion[];
  whatIfPresets: WhatIfPreset[];
  chartMetrics: string[];
  exploreBasePath: string;
}
