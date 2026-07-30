/** Platform-core query param for comma-separated task type allowlists (GET APIs). */
export const TASK_TYPES_QUERY_PARAM = "task_types";

export function taskTypesQueryValue(
  names: string[] | null | undefined,
): string | undefined {
  if (!names?.length) return undefined;
  return names.join(",");
}

export function appendTaskTypesToSearchParams(
  params: URLSearchParams,
  names: string[] | null | undefined,
): void {
  const value = taskTypesQueryValue(names);
  if (value) params.set(TASK_TYPES_QUERY_PARAM, value);
}

export function withTaskTypesQueryRecord(
  query: Record<string, string | number>,
  csv: string | null | undefined,
): Record<string, string | number> {
  const value = csv?.trim();
  if (value) query[TASK_TYPES_QUERY_PARAM] = value;
  return query;
}
