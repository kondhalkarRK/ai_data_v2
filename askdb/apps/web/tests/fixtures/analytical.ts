/** Visible synthetic UI fixture. No client data, model calls or acceptance holdouts. */
import type { AnalyticalColumn, ChatMessage, ResponseMeta } from "@/components/chat/types";

const money: AnalyticalColumn = { key: "revenue", label: "Revenue", kind: "currency", role: "value" };
const region: AnalyticalColumn = { key: "region", label: "Region", kind: "text", role: "dimension" };
const model: AnalyticalColumn = { key: "model", label: "Model", kind: "text", role: "dimension" };
const searchPeriod = { label: "Q1 2026", start: "2026-01-01", endExclusive: "2026-04-01" };
const meta: ResponseMeta = {
  responseKind: "data", runId: "run-analysis", groundedOn: ["Semantic Layer"], ambiguityFlag: false,
  validationStatus: "passed", rowCount: 5, executionTimeMs: 12, sourceDatabase: "Fixture",
  dataAsOf: "2026-03-31", timings: { llmGenerationMs: 1, semanticLookupMs: 1, sqlValidationMs: 1, executionMs: 12, renderMs: 1 },
  queryMeta: { tablesUsed: [], metricsUsed: [], dimensionsUsed: [], joinPath: [], filtersApplied: [], dateRange: null },
  insights: { executive: "South leads; its models follow.", analyst: "" }, anomalies: [], alternateInterpretations: [],
  runUsage: { initialModelCalls: 1, verificationModelCalls: 1, analyticalQueries: 1 },
  analyticalAudit: { runId: "run-analysis", status: "completed", semanticVersion: "fixture:1", scopeFingerprint: "scope-fingerprint", sqlFingerprint: "sql-fingerprint", analysisDate: "2026-04-01" },
  analyticalPresentation: {
    version: 1, status: "completed", summary: "South leads on revenue. Its models are shown below.",
    scope: ["All permitted regions"], notes: [], checks: [], unanswered: [],
    steps: [
      { id: "totals", title: "Revenue by region", operation: "aggregate", dependsOn: [], status: "completed", verified: true,
        summary: "Two matching regions.", columns: [region, money], displayedRows: 2, totalGroups: 2, selectedGroups: 2,
        notes: [], searchPeriod, comparisonPeriods: [], filters: [] },
      { id: "leader", title: "Highest revenue region", operation: "select_extreme", dependsOn: ["totals"], status: "completed", verified: true,
        summary: "South: ₹3.00 Cr.", columns: [region, money], displayedRows: 1, totalGroups: 1, selectedGroups: 1,
        notes: [], searchPeriod, comparisonPeriods: [] },
      { id: "models", title: "Revenue by model in selected region", operation: "aggregate", dependsOn: ["leader"], status: "completed", verified: true,
        summary: "Two matching models within South.", columns: [model, money], displayedRows: 2, totalGroups: 2, selectedGroups: 2,
        notes: [], searchPeriod, comparisonPeriods: [], filters: [] },
    ],
  },
  analyticalExecution: { status: "completed", message: "", scope_labels: ["All permitted regions"], steps: [
    { id: "totals", status: "completed", columns: ["region", "revenue"], rows: [{ region: "South", revenue: 30000000 }, { region: "West", revenue: 20000000 }], verified: true, total_groups: 2, selected_groups: 2, notes: [] },
    { id: "leader", status: "completed", columns: ["region", "revenue"], rows: [{ region: "South", revenue: 30000000 }], verified: true, total_groups: 1, selected_groups: 1, notes: [] },
    { id: "models", status: "completed", columns: ["model", "revenue"], rows: [{ model: "Alpha", revenue: "20000000.01" }, { model: "Beta", revenue: 9999999.99 }], verified: true, total_groups: 2, selected_groups: 2, notes: [] },
  ] },
  analyticalPlan: { steps: [
    { id: "totals", label: "Revenue by region", operation: "aggregate", depends_on: [], outputs: [{ name: "region", role: "dimension", semantic_id: "dim_region.region_name", value_type: "string" }, { name: "revenue", role: "value", semantic_id: "revenue", value_type: "decimal" }] },
    { id: "leader", label: "Highest revenue region", operation: "select_extreme", depends_on: ["totals"], outputs: [{ name: "region", role: "dimension", semantic_id: "dim_region.region_name", value_type: "string" }, { name: "revenue", role: "value", semantic_id: "revenue", value_type: "decimal" }] },
    { id: "models", label: "Revenue by model in selected region", operation: "aggregate", depends_on: ["leader"], outputs: [{ name: "model", role: "dimension", semantic_id: "dim_carline.model", value_type: "string" }, { name: "revenue", role: "value", semantic_id: "revenue", value_type: "decimal" }] },
  ] },
};

export function analyticalMessage(partial = false): ChatMessage {
  const message: ChatMessage = { id: "analysis-response", role: "assistant", complete: true,
    historyId: "11111111-1111-4111-8111-111111111111", sql: "WITH approved AS (SELECT 1) SELECT * FROM approved",
    narrative: "South leads on revenue.", meta: structuredClone(meta) };
  if (partial) {
    message.meta!.responseKind = "partial";
    const view = message.meta!.analyticalPresentation!;
    view.status = "partial";
    view.summary = "The selected region is available; model attribution could not be verified.";
    view.steps[2]!.status = "partial";
    view.steps[2]!.verified = false;
    view.steps[2]!.summary = "Contributing factors could not be verified.";
    view.steps[2]!.notes = ["Independent totals did not reconcile."];
    view.checks = [{ passed: false, measure: "revenue" }];
    message.meta!.analyticalExecution!.status = "partial";
    message.meta!.analyticalExecution!.steps[2]!.status = "partial";
    message.meta!.analyticalExecution!.steps[2]!.verified = false;
  }
  return message;
}
