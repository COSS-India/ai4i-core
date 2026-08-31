/** Normalise API task-type ids to yaml/hyphen form (matches `useInferenceTypes`). */
export function normalizeModelTaskType(value: string | null | undefined): string {
  if (!value?.trim()) return "";
  return value.trim().toLowerCase().replace(/_/g, "-");
}
