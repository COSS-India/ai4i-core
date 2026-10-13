/** Exact token count for an LLM drill-down row (en-IN grouping). */
export function formatTokenCount(value: number): string {
  return value.toLocaleString("en-IN");
}
