// Model version and task-type registry constants

/** Model version lifecycle (model-management). */
export const MODEL_VERSION = {
  STATUS: {
    ACTIVE: "ACTIVE",
    DEPRECATED: "DEPRECATED",
  },
  FILTER: {
    ALL: "",
    ACTIVE: "active",
    DEPRECATED: "deprecated",
  },
} as const;

export const MODEL_VERSION_FILTER_LIST: readonly (typeof MODEL_VERSION.FILTER)[keyof typeof MODEL_VERSION.FILTER][] =
  [MODEL_VERSION.FILTER.ACTIVE, MODEL_VERSION.FILTER.DEPRECATED];

export function isModelVersionStatusActive(status?: string | null): boolean {
  const normalized = (status ?? MODEL_VERSION.STATUS.ACTIVE).trim().toUpperCase();
  return normalized === MODEL_VERSION.STATUS.ACTIVE || normalized === "";
}

export function isModelVersionFilterStatus(
  actual: string,
  expected: (typeof MODEL_VERSION.FILTER)[keyof typeof MODEL_VERSION.FILTER]
): boolean {
  return actual.trim().toLowerCase() === expected;
}

export function formatModelVersionStatusLabel(status?: string | null): string {
  return isModelVersionStatusActive(status) ? "Active" : "Deprecated";
}

export function isModelVersionStatusDeprecated(status?: string | null): boolean {
  if (!status?.trim()) return false;
  return status.trim().toUpperCase() === MODEL_VERSION.STATUS.DEPRECATED;
}

export function formatModelVersionFilterLabel(filter: string): string {
  if (isModelVersionFilterStatus(filter, MODEL_VERSION.FILTER.ACTIVE)) return "Active";
  if (isModelVersionFilterStatus(filter, MODEL_VERSION.FILTER.DEPRECATED)) return "Deprecated";
  return filter;
}

/**
 * Inference task types (platform TaskTypeEnum).
 * Static list for model/service registry task-type filters.
 */
export const MODEL_TASK_TYPE_LIST = [
  "asr",
  "nmt",
  "tts",
  "llm",
  "transliteration",
  "language-detection",
  "speaker-diarization",
  "audio-lang-detection",
  "language-diarization",
  "ocr",
  "ner",
] as const;

export type ModelTaskTypeValue = (typeof MODEL_TASK_TYPE_LIST)[number];

/** Display label for task-type filter options (matches table badges). */
export function formatModelTaskTypeLabel(taskType: string): string {
  return taskType.trim().toUpperCase();
}
