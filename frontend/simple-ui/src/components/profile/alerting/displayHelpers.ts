import { ALERT_TYPES_BY_CATEGORY } from "./constants";

export function severityColor(s: string) {
  switch (s) {
    case "critical": return "red";
    case "warning": return "orange";
    case "info": return "blue";
    default: return "gray";
  }
}

export function categoryColor(c: string | null | undefined) {
  if (c === "application") return "orange";
  if (c === "infrastructure") return "purple";
  return "gray";
}

export const titleCase = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();

export function alertTypeLabel(val: string | null | undefined) {
  if (!val) return "—";
  for (const types of Object.values(ALERT_TYPES_BY_CATEGORY)) {
    const found = types.find((t) => t.value === val);
    if (found) return found.label;
  }
  return val.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatThreshold(d: { threshold_value?: number | null; threshold_unit?: string | null; promql_expr?: string }) {
  const val = d.threshold_value;
  const unit = (d.threshold_unit || "").trim().toLowerCase();
  if (typeof val === "number" && !Number.isNaN(val)) {
    if (unit === "percentage") return `${val}%`;
    if (unit === "seconds") return `${val} s`;
    if (unit) return `${val} ${(d.threshold_unit || "").trim()}`;
    return String(val);
  }
  return d.promql_expr || "—";
}
