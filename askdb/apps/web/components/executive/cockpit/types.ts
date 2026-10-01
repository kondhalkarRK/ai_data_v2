export interface CockpitFilters {
  year?: string;
  quarter?: string;
  month?: string;
  make?: string;
  model?: string;
  engine_type?: string;
  car_type?: string;
  zone?: string;
  state?: string;
  city?: string;
  dealer_id?: string;
  sales_person_id?: string;
}

export type FilterKey = keyof CockpitFilters;

export interface MetricKpi {
  value: number;
  prior: number;
  growth: number | null;
}

export interface LeaderKpi {
  name: string;
  make: string | null;
  revenue: number;
  share: number;
  shareChange: number | null;
  growth: number | null;
}

export interface TrendPoint {
  month: string;
  revenue: number | null;
  units: number | null;
  priorRevenue: number | null;
  forecastRevenue: number | null;
  forecastUnits: number | null;
  inPeriod: boolean;
  partial: boolean;
  peak: boolean;
  growthPeriod: boolean;
}

export interface TrendEvent {
  month: string;
  label: string;
  kind: "festive" | "shock";
}

export interface RankedItem {
  key: string;
  name: string;
  detail: string | null;
  group: string | null;
  revenue: number;
  units: number;
  priorRevenue: number;
  growth: number | null;
  share: number;
  priorShare: number | null;
}

export interface SunburstNode {
  name: string;
  dimension: "make" | "model" | "engine_type";
  revenue: number;
  units: number;
  children: SunburstNode[];
}

export interface HeatMatrix {
  rows: string[];
  cols: string[];
  cells: Array<{ row: string; col: string; revenue: number; share: number; growth: number | null }>;
}

export interface BulletMetric {
  label: string;
  actual: number;
  target: number | null;
  achievement: number | null;
  format: "currency" | "integer";
}

export interface CockpitInsight {
  id: string;
  tone: "positive" | "negative" | "neutral";
  headline: string;
  detail: string;
  metric: string | null;
  filterDimension: FilterKey | null;
  filterValue: string | null;
}

export interface CockpitData {
  period: {
    label: string;
    start: string;
    end: string;
    priorLabel: string;
    priorStart: string;
    priorEnd: string;
    dataAsOf: string;
    planMonthsLabel: string | null;
  };
  appliedFilters: Record<string, string>;
  empty: boolean;
  kpis: {
    revenue: MetricKpi;
    units: MetricKpi;
    orders: MetricKpi;
    avgPrice: MetricKpi;
    topModel: LeaderKpi | null;
    topMake: LeaderKpi | null;
  };
  trend: TrendPoint[];
  events: TrendEvent[];
  zones: RankedItem[];
  states: RankedItem[];
  cities: RankedItem[];
  dealers: RankedItem[];
  sunburst: SunburstNode[];
  topModelsByRevenue: RankedItem[];
  topModelsByUnits: RankedItem[];
  fuelMix: RankedItem[];
  bodyMix: RankedItem[];
  heat: HeatMatrix;
  plan: {
    monthsLabel: string | null;
    revenue: BulletMetric;
    units: BulletMetric;
    forecastRevenue: BulletMetric;
    forecastUnits: BulletMetric;
    targetNote: string | null;
    forecastNote: string | null;
    byMake: Array<{ make: string; actualUnits: number; targetUnits: number; achievement: number }>;
  };
  insights: CockpitInsight[];
  computedAt: string;
}

export interface OptionItem {
  value: string;
  label: string;
  group: string | null;
}

export interface CockpitOptions {
  years: number[];
  makes: OptionItem[];
  models: OptionItem[];
  engineTypes: OptionItem[];
  carTypes: OptionItem[];
  zones: OptionItem[];
  states: OptionItem[];
  dealers: OptionItem[];
  salespeople: OptionItem[];
}

/** Lets a chart narrow the whole dashboard (cross filtering). */
export type SelectHandler = (key: FilterKey, value: string) => void;
