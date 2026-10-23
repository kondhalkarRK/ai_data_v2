/** Format chat result table/chart values; period columns show YYYY-MM not YYYY-MM-DD. */

const PERIOD_COLUMN = /^(month|quarter|half|period|year_month|time_period)$/i;
const PERIOD_COLUMN_SUFFIX = /_(month|quarter|half|period)$/i;
const ISO_DATE = /^(\d{4}-\d{2}-\d{2})/;

export function isPeriodColumn(column: string): boolean {
  const key = column.trim();
  if (PERIOD_COLUMN.test(key)) return true;
  if (PERIOD_COLUMN_SUFFIX.test(key)) return true;
  if (/quarter/i.test(key) && !/growth/i.test(key)) return true;
  if (/half/i.test(key) && !/growth/i.test(key)) return true;
  return false;
}

export function formatChatCell(value: unknown, column: string): string {
  if (value == null || value === "") return "—";
  const text = String(value);
  if (!isPeriodColumn(column)) return text;
  if (/^\d{4}-\d{2}$/.test(text)) return text;
  const match = ISO_DATE.exec(text);
  if (match) return match[1]!.slice(0, 7);
  return text;
}
