import type { DataTableColumnFilters } from "../common/table";
import type { ModelListParams } from "../../types/platform";

/**
 * Filter ids the Model List page sends to GET /models/list: the name search and
 * the Status / Task Type toolbar filters. Anything else is dropped.
 */
export const MODEL_SERVER_SEARCH_COLUMN_IDS: ReadonlySet<string> = new Set([
  "name",
  "taskType",
  "status",
]);

/** Sortable columns on the Model List page, sent as `sort_by` (backend SORTABLE_KEYS). */
const MODEL_SORTABLE_COLUMN_IDS: ReadonlySet<string> = new Set([
  "name",
  "version",
  "taskType",
  "providerName",
  "status",
  "createdAt",
  "noOfServices",
]);

/** Only the filters the API understands, so anything else never refetches. */
export function modelServerFilters(
  filters: DataTableColumnFilters,
): DataTableColumnFilters {
  const next: DataTableColumnFilters = {};
  for (const [id, value] of Object.entries(filters)) {
    const trimmed = value.trim();
    if (trimmed && MODEL_SERVER_SEARCH_COLUMN_IDS.has(id)) next[id] = trimmed;
  }
  return next;
}

/**
 * GET /models/list params for one page of the Model List.
 * No task type picked → every enabled task type, so disabled types never show.
 */
export function buildModelListParams(options: Readonly<{
  filters: DataTableColumnFilters;
  enabledTaskTypes: readonly string[];
  sort: { key: string; direction: "asc" | "desc" };
  page: number;
  pageSize: number;
  columns: string;
}>): ModelListParams {
  const { filters, enabledTaskTypes, sort, page, pageSize, columns } = options;
  const server = modelServerFilters(filters);
  const taskTypes = server.taskType || enabledTaskTypes.join(",");
  const sortBy = MODEL_SORTABLE_COLUMN_IDS.has(sort.key) ? sort.key : undefined;
  return {
    offset: Math.max(0, page - 1) * pageSize,
    limit: pageSize,
    columns: columns || undefined,
    name: server.name,
    versionStatus: server.status,
    taskTypes: taskTypes || undefined,
    sortBy,
    sortOrder: sortBy ? sort.direction : undefined,
  };
}
