import { METERING } from "../config/meteringConstants";

/** Normalise task-type ids to yaml/hyphen form (matches `useInferenceTypes`). */
export function normalizeModelTaskType(value: string): string {
  return value.trim().toLowerCase().replace(/_/g, "-");
}

const DISPLAY_NAME_TO_TASK_KEY = Object.fromEntries(
  Object.entries(METERING.SERVICE_CSS_KEYS).map(([display, key]) => [
    display.trim().toLowerCase(),
    key,
  ]),
) as Record<string, string>;

/**
 * Infer model task type from a model-consumption service row (FE-only until BE
 * adds an explicit `task_type` field on ServiceModelRow).
 */
export function inferModelTaskType(
  serviceId: string,
  serviceName?: string | null,
): string {
  const idPrefix = serviceId.split("/")[0]?.trim();
  if (idPrefix && /^[a-z][a-z0-9_-]*$/i.test(idPrefix)) {
    return normalizeModelTaskType(idPrefix);
  }

  const name = (serviceName ?? "").trim();
  if (name) {
    const fromDisplay = DISPLAY_NAME_TO_TASK_KEY[name.toLowerCase()];
    if (fromDisplay) return normalizeModelTaskType(fromDisplay);
    if (/^[a-z][a-z0-9_-]*$/i.test(name)) return normalizeModelTaskType(name);
  }

  return "";
}

export function enrichModelConsumptionRows<
  T extends { service_id: string; name: string; model_name?: string | null },
>(rows: T[]): Array<T & { task_type: string }> {
  return rows.map((row) => ({
    ...row,
    task_type: inferModelTaskType(row.service_id, row.name),
  }));
}

/** First task type seen for each model name in the breakdown (for donut labels). */
export function taskTypeByModelName(
  rows: Array<{ model_name?: string | null; task_type: string }>,
): Map<string, string> {
  const map = new Map<string, string>();
  for (const row of rows) {
    const modelName = row.model_name?.trim();
    if (!modelName || map.has(modelName) || !row.task_type) continue;
    map.set(modelName, row.task_type);
  }
  return map;
}
