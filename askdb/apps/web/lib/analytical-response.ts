/** Presentation only. No requests, routing, analytical calculations or date rebasing. */
import type { AnalyticalColumn, AnalyticalPresentation, ChatMessage } from "@/components/chat/types";

export function analyticalPresentation(message: ChatMessage): AnalyticalPresentation | null {
  if (message.cancelled || message.error || message.failure || ["denied", "failed", "cancelled", "unavailable"].includes(message.meta?.responseKind ?? "")) return null;
  const execution = message.meta?.analyticalExecution;
  if (!execution || !Array.isArray(execution.steps) || !["completed", "partial", "clarification", "empty"].includes(execution.status)) return null;
  const view = message.meta?.analyticalPresentation;
  if (view?.version === 1 && Array.isArray(view.steps) && view.steps.every(step => typeof step.title === "string" && Array.isArray(step.columns))) return view;
  // Batch 2 snapshots predate the display DTO. Preserve their actual values and
  // states; never ask the server to rerun them or resolve relative dates today.
  const plan = message.meta?.analyticalPlan;
  if (!plan || !Array.isArray(plan.steps)) return null;
  return {
    version: 1, legacy: true, status: execution.status,
    summary: execution.message || (execution.status === "empty" ? "No matching records. This does not establish a zero result." : execution.status === "clarification" ? "Narrow the selection to preserve all tied members." : "Saved multi-step analysis. Some display details are unavailable for this older response."),
    scope: execution.scope_labels ?? ["Your permitted regions"], notes: [], checks: [], unanswered: [],
    steps: execution.steps.map(step => {
      const definition = plan.steps.find(item => item.id === step.id);
      return { id: step.id, title: definition?.label.replaceAll("_", " ") || "Analysis step",
        operation: definition?.operation ?? "aggregate", dependsOn: definition?.depends_on ?? [],
        status: step.status, verified: step.verified, completenessVerified: step.completeness_verified,
        summary: step.verified ? "Saved observations are shown below." : "This part was not verified.",
        columns: (step.columns ?? []).map(key => {
          const output = definition?.outputs.find(item => item.name === key);
          const kind = output?.role === "percent_change" ? "percent" : /revenue|price|asp|amount|cost/i.test(output?.semantic_id ?? key) && output?.role !== "rank" ? "currency" : output?.value_type === "date" || /period_(?:start|end)$/.test(key) ? "date" : ["decimal", "integer"].includes(output?.value_type ?? "") ? "number" : "text";
          return { key, kind, role: output?.role, semanticId: output?.semantic_id, label: key.replaceAll("_", " ") };
        }), displayedRows: step.rows?.length ?? 0, totalGroups: step.total_groups,
        selectedGroups: step.selected_groups ?? step.rows?.length ?? 0,
        notes: step.notes ?? [], comparisonPeriods: [],
      };
    }),
  };
}

export function formatAnalyticalCell(value: unknown, column: AnalyticalColumn): string {
  if (value == null || value === "") return "Unavailable";
  if (["text", "date"].includes(column.kind)) return String(value);
  if (typeof value === "boolean" || !Number.isFinite(Number(value))) return "Unavailable";
  const number = Number(value);
  if (column.kind === "percent") return `${number.toFixed(1)}%`;
  const size = Math.abs(number);
  const sign = number < 0 ? "-" : "";
  const prefix = column.kind === "currency" ? "₹" : "";
  const formatted = size >= 1e7 ? `${(size / 1e7).toFixed(2)} Cr`
    : size >= 1e5 ? `${(size / 1e5).toFixed(2)} ${column.kind === "currency" ? "Lakh" : "L"}`
    : size >= 1000 ? new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(size)
    : Number.isInteger(size) ? String(size) : size.toFixed(2);
  return `${sign}${prefix}${formatted}`;
}
