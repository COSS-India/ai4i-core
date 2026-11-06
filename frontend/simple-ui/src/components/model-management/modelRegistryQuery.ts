import { parseDateRangeFilter } from "../common/DataTableColumnFilter";
import type { DataTableColumnFilters } from "../common/table";
import type { ModelListParams } from "../../types/platform";

/** Filter ids (column keys) GET /models/list can filter on; others are dropped. */
export const MODEL_SERVER_SEARCH_COLUMN_IDS: ReadonlySet<string> = new Set([
  "name",
  "version",
  "taskType",
  "providerName",
  "status",
  "createdAt",
]);

/** Column ids GET /models/list accepts as `sort_by`. */
const MODEL_SORTABLE_COLUMN_IDS: ReadonlySet<string> = new Set([
  ...Array.from(MODEL_SERVER_SEARCH_COLUMN_IDS),
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
  const { from, to } = parseDateRangeFilter(server.createdAt ?? "");
  const taskTypes = server.taskType || enabledTaskTypes.join(",");
  const sortBy = MODEL_SORTABLE_COLUMN_IDS.has(sort.key) ? sort.key : undefined;
  return {
    offset: Math.max(0, page - 1) * pageSize,
    limit: pageSize,
    columns: columns || undefined,
    name: server.name,
    version: server.version,
    providerName: server.providerName,
    versionStatus: server.status,
    taskTypes: taskTypes || undefined,
    createdFrom: from || undefined,
    createdTo: to || undefined,
    sortBy,
    sortOrder: sortBy ? sort.direction : undefined,
  };
}
