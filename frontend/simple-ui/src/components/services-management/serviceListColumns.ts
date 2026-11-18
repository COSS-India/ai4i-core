/**
 * Service List column catalogue and per-user selection (AI4IDS-3356).
 *
 * `SERVICE_LIST_COLUMNS` holds every column with the filter metadata
 * `GET /services` needs; its ids are the API column ids. The `service-column`
 * config (AI4IDS-3732), as for the Model List, sets which columns appear,
 * their order, labels and which are mandatory (`required`). Sortable columns
 * are fixed in SERVICE_SORTABLE_COLUMN_IDS, as for the Model List.
 * Each user's column selection is kept in browser storage only, as for the
 * Model List.
 */

import type { ServiceColumnConfigEntry } from "../../services/configManagementService";
import type { Service } from "../../types/platform";
import { resolveTaskType } from "../../utils/platformService";
import {
  canToggleOffColumn,
  resolveColumnSelection,
  toggleColumnSelection,
} from "../common/adminListColumnSelection";

/** API column ids (`GET /services?columns=`, column preferences). */
export type ServiceListColumnId =
  | "name"
  | "task_type"
  | "model_name"
  | "tier"
  | "status"
  | "created_at"
  | "service_id"
  | "input_price"
  | "output_price"
  | "cached_input_price"
  | "published_at"
  | "actions";

export type ServiceListColumnFilter = {
  type: string;
  params: string[];
  options: { value: string; label: string }[] | null;
};

export type ServiceListColumnDef = {
  id: string;
  label: string;
  /**
   * Always visible; the picker cannot turn these off. They are also the
   * default selection (first visit and Reset to default).
   */
  mandatory: boolean;
  filterable?: boolean;
  filter?: ServiceListColumnFilter | null;
};

/** Cell renderer key. API ids are snake_case; `service-column` config keys may be camelCase. */
const CELL_KEYS: Record<string, string> = {
  name: "name",
  actions: "actions",
  task_type: "task",
  modelTaskType: "task",
  tier: "tier",
  status: "status",
  created_at: "createdAt",
  createdAt: "createdAt",
  model_name: "modelName",
  modelName: "modelName",
  service_id: "serviceId",
  serviceId: "serviceId",
  input_price: "inputPrice",
  inputPrice: "inputPrice",
  output_price: "outputPrice",
  outputPrice: "outputPrice",
  cached_input_price: "cachedInputPrice",
  cachedInputPrice: "cachedInputPrice",
  published_at: "publishedOn",
  published_on: "publishedOn",
  publishedOn: "publishedOn",
};

export function serviceListCellKey(id: string): string {
  return CELL_KEYS[id] ?? id;
}

function serviceFilter(
  type: string,
  params: string[],
  options: ServiceListColumnFilter["options"] = null,
): ServiceListColumnFilter {
  return { type, params, options };
}

function serviceColumn(
  id: ServiceListColumnId,
  label: string,
  mandatory: boolean,
  filter?: ServiceListColumnFilter,
): ServiceListColumnDef {
  return filter ? { id, label, mandatory, filterable: true, filter } : { id, label, mandatory };
}

/**
 * Every Service List column, in the built-in display order (used when the
 * `service-column` config is missing). Mirrors platform-core's
 * `SERVICE_LIST_COLUMNS` (app/schemas/model_management/service_columns.py):
 * ids and filter query params must match it. Only Admins and
 * Adopter Admins open Services Management, and they get every column.
 * Actions stay last, matching the rest of the admin tables.
 */
export const SERVICE_LIST_COLUMNS: readonly ServiceListColumnDef[] = [
  serviceColumn("name", "Name", true, serviceFilter("text", ["name"])),
  // Task type options come from the enabled task types (useInferenceTypes).
  serviceColumn("task_type", "Task Type", true, serviceFilter("multi_select", ["task_types"])),
  serviceColumn("model_name", "Model Name", true, serviceFilter("text", ["model_name"])),
  // Tier options come from the active tiers (tierFilterOptions).
  serviceColumn("tier", "Tier", true, serviceFilter("multi_select", ["tier_ids"])),
  serviceColumn(
    "status",
    "Status",
    false,
    serviceFilter("single_select", ["is_published"], [
      { value: "true", label: "Published" },
      { value: "false", label: "Unpublished" },
    ]),
  ),
  serviceColumn(
    "created_at",
    "Created At",
    false,
    serviceFilter("date_range", ["created_from", "created_to"]),
  ),
  serviceColumn("service_id", "Service ID", false, serviceFilter("text", ["service_id"])),
  serviceColumn("input_price", "Input Price", false),
  serviceColumn("output_price", "Output Price", false),
  serviceColumn("cached_input_price", "Cached Input Price", false),
  serviceColumn(
    "published_at",
    "Published On",
    false,
    serviceFilter("date_range", ["published_from", "published_to"]),
  ),
  serviceColumn("actions", "Actions", true),
];

/**
 * Sortable columns on the Service List, sent as `sort_by` (backend
 * SORTABLE_KEYS in service_columns.py). Actions is not sortable.
 */
export const SERVICE_SORTABLE_COLUMN_IDS: ReadonlySet<string> = new Set([
  "name",
  "task_type",
  "tier",
  "status",
  "created_at",
  "model_name",
  "service_id",
  "input_price",
  "output_price",
  "cached_input_price",
  "published_at",
]);

export const SERVICE_LIST_COLUMN_STORAGE_PREFIX = "service-list-columns";

/** Missing dates and prices sort after real values when the column is ascending. */
const MISSING_SORT_VALUE = Number.POSITIVE_INFINITY;

/** The default selection: the mandatory columns only. Optional columns start hidden. */
export function defaultServiceListColumnIds(
  catalogue: readonly ServiceListColumnDef[] = SERVICE_LIST_COLUMNS,
): string[] {
  return catalogue.filter((column) => column.mandatory).map((column) => column.id);
}

export function resolveServiceListColumns(
  selected: readonly string[] | null | undefined,
  catalogue: readonly ServiceListColumnDef[] = SERVICE_LIST_COLUMNS,
): string[] {
  return resolveColumnSelection(selected, catalogue, defaultServiceListColumnIds);
}

export function canToggleOffServiceListColumn(
  _current: readonly string[],
  id: string,
  catalogue: readonly ServiceListColumnDef[] = SERVICE_LIST_COLUMNS,
): boolean {
  return canToggleOffColumn(id, catalogue);
}

export function toggleServiceListColumn(
  current: readonly string[],
  id: string,
  catalogue: readonly ServiceListColumnDef[] = SERVICE_LIST_COLUMNS,
): string[] {
  return toggleColumnSelection(current, id, catalogue, defaultServiceListColumnIds);
}

/**
 * Apply the `service-column` config to the catalogue. Entries are matched to
 * catalogue columns by cell, so the config's keys may be camelCase
 * (`modelTaskType`) or API ids (`task_type`); the catalogue's ids are kept, as
 * `GET /services?columns=` and the saved selection need them. The config sets
 * which columns appear, their order, labels and which are mandatory
 * (`required`); any `defaultVisible` flag is ignored. Sorting and filters
 * stay with the catalogue. Entries the catalogue lacks are ignored, and
 * Actions is appended, as mandatory, if left out. Without a usable config the
 * catalogue is used as it is.
 */
export function serviceListColumnsFromConfig(
  catalogue: readonly ServiceListColumnDef[],
  entries: readonly ServiceColumnConfigEntry[] | null | undefined,
): readonly ServiceListColumnDef[] {
  const byCell = new Map(catalogue.map((column) => [serviceListCellKey(column.id), column]));
  const used = new Set<string>();
  const configured: ServiceListColumnDef[] = [];
  for (const entry of entries ?? []) {
    const cell = serviceListCellKey(entry.key);
    const column = byCell.get(cell);
    if (column == null || used.has(cell)) continue;
    used.add(cell);
    configured.push({ ...column, label: entry.label, mandatory: entry.required });
  }
  if (configured.length === 0) return catalogue;
  const actions = byCell.get("actions");
  if (actions && !used.has("actions")) configured.push({ ...actions, mandatory: true });
  return configured;
}

export type ServiceListColumnPreferenceStore = {
  read: (userId: string) => string[] | null;
  write: (userId: string, columnIds: readonly string[]) => void;
};

export function serviceListColumnStorageKey(userId: string): string {
  return `${SERVICE_LIST_COLUMN_STORAGE_PREFIX}:${userId}`;
}

export const browserServiceListColumnStore: ServiceListColumnPreferenceStore = {
  read(userId) {
    if (globalThis.window === undefined || !userId) return null;
    try {
      const raw = globalThis.window.localStorage.getItem(
        serviceListColumnStorageKey(userId),
      );
      if (!raw) return null;
      const parsed: unknown = JSON.parse(raw);
      if (!Array.isArray(parsed) || !parsed.every((id) => typeof id === "string")) {
        return null;
      }
      return parsed;
    } catch {
      return null;
    }
  },
  write(userId, columnIds) {
    if (globalThis.window === undefined || !userId) return;
    try {
      globalThis.window.localStorage.setItem(
        serviceListColumnStorageKey(userId),
        JSON.stringify(columnIds),
      );
    } catch {
      // Private mode or a full quota: the selection still applies for this visit.
    }
  },
};

/** Keys used when a column filter is `date_range` (from / to). */
export function serviceListRangeFilterKeys(columnId: string): {
  from: string;
  to: string;
} {
  return { from: `${columnId}__from`, to: `${columnId}__to` };
}

export function loadServiceListColumns(
  userId: string,
  store: ServiceListColumnPreferenceStore = browserServiceListColumnStore,
  catalogue: readonly ServiceListColumnDef[] = SERVICE_LIST_COLUMNS,
): string[] {
  if (!userId) return defaultServiceListColumnIds(catalogue);
  return resolveServiceListColumns((store ?? browserServiceListColumnStore).read(userId), catalogue);
}

export function saveServiceListColumns(
  userId: string,
  columnIds: readonly string[],
  store: ServiceListColumnPreferenceStore = browserServiceListColumnStore,
  catalogue: readonly ServiceListColumnDef[] = SERVICE_LIST_COLUMNS,
): string[] {
  const resolved = resolveServiceListColumns(columnIds, catalogue);
  if (userId) (store ?? browserServiceListColumnStore).write(userId, resolved);
  return resolved;
}

/**
 * Convert a `YYYY-MM-DD` date-picker value to an ISO instant with local offset
 * for `GET /services` date_range filters.
 *
 * Prefer offset form (e.g. `2026-10-26T00:00:00+05:30`) so the bound matches
 * the local calendar day shown in the table. `to` is the next local midnight
 * (exclusive). Bare `YYYY-MM-DD` on the API is a whole UTC day and drifts.
 */
export function serviceListDateFilterInstant(
  dateValue: string,
  bound: "from" | "to",
): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateValue)) return null;
  const local = new Date(`${dateValue}T00:00:00`);
  if (Number.isNaN(local.getTime())) return null;
  if (bound === "to") {
    local.setDate(local.getDate() + 1);
  }
  return formatLocalOffsetIso(local);
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

/** Local wall time + numeric offset (`±HH:MM`), not UTC `Z`. */
function formatLocalOffsetIso(date: Date): string {
  const offsetMinutes = -date.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const abs = Math.abs(offsetMinutes);
  return (
    `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}` +
    `T${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}` +
    `${sign}${pad2(Math.floor(abs / 60))}:${pad2(abs % 60)}`
  );
}

function applyDateRangeFilterParams(
  column: ServiceListColumnDef,
  filters: Record<string, string>,
  params: Record<string, string>,
): void {
  const filterParams = column.filter?.params ?? [];
  if (filterParams.length < 2) return;
  const keys = serviceListRangeFilterKeys(column.id);
  const from = (filters[keys.from] ?? "").trim();
  const to = (filters[keys.to] ?? "").trim();
  const fromIso = from ? serviceListDateFilterInstant(from, "from") : null;
  const toIso = to ? serviceListDateFilterInstant(to, "to") : null;
  if (fromIso) params[filterParams[0]] = fromIso;
  if (toIso) params[filterParams[1]] = toIso;
}

/** multi_select: one or more option values, comma-separated (any-of). */
function normalizeMultiSelectFilterValue(value: string): string {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean)
    .join(",");
}

function applyColumnFilterParam(
  column: ServiceListColumnDef,
  filters: Record<string, string>,
  params: Record<string, string>,
): string | null {
  const param = column.filter?.params[0];
  if (!param) return null;
  let value = (filters[column.id] ?? "").trim();
  if (column.filter?.type === "multi_select" && value) {
    value = normalizeMultiSelectFilterValue(value);
  }
  const isTask =
    serviceListCellKey(column.id) === "task" || param === "task_types";
  if (value) params[param] = value;
  if (isTask) return param;
  return null;
}

export function serviceListFilterParams(options: {
  columns: readonly ServiceListColumnDef[];
  filters: Record<string, string>;
  enabledTaskTypes?: string;
  sortBy?: string;
  sortOrder?: "asc" | "desc";
}): Record<string, string> {
  const params: Record<string, string> = {};
  let taskParam: string | null = null;
  for (const column of options.columns) {
    if (!column.filterable || !column.filter) continue;
    if (column.filter.type === "date_range") {
      applyDateRangeFilterParams(column, options.filters, params);
      continue;
    }
    const maybeTask = applyColumnFilterParam(column, options.filters, params);
    if (maybeTask) taskParam = maybeTask;
  }
  if (taskParam && !params[taskParam] && options.enabledTaskTypes) {
    params[taskParam] = options.enabledTaskTypes;
  } else if (!taskParam && options.enabledTaskTypes) {
    params.task_types = options.enabledTaskTypes;
  }
  if (options.sortBy) {
    params.sort_by = options.sortBy;
    params.sort_order = options.sortOrder ?? "asc";
  }
  return params;
}

/** ISO timestamp → epoch ms; 0 when missing or unparseable. */
function isoToMillis(raw: string | null | undefined): number {
  if (typeof raw !== "string" || !raw.trim()) return 0;
  const ms = Date.parse(raw);
  return Number.isNaN(ms) ? 0 : ms;
}

// API emits camelCase; snake_case kept as a legacy fallback.
export function serviceCreatedAtMillis(service: Service): number {
  return isoToMillis(service.createdAt ?? service.created_at);
}

export function serviceUpdatedAtMillis(service: Service): number {
  return isoToMillis(service.updatedAt ?? service.updated_at);
}

export function servicePublishedOnMillis(service: Service): number {
  // List API emits ISO `publishedAt`; `publishedOn` is only set by the local
  // publish/unpublish optimistic patch in this tab.
  const fromIso = isoToMillis(service.publishedAt);
  if (fromIso) return fromIso;
  const raw = service.publishedOn;
  if (raw == null || !Number.isFinite(raw) || raw <= 0) return 0;
  return raw < 1e12 ? raw * 1000 : raw;
}

export function serviceModelName(service: Service): string {
  return (
    service.model?.name ||
    service.modelName ||
    service.modelId ||
    service.model_id ||
    ""
  );
}

export function serviceListServiceId(service: Service): string {
  return service.serviceId || service.service_id || "";
}

export function formatServiceListDate(ms: number): string {
  if (!ms) return "—";
  const date = new Date(ms);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

export function formatServiceListPrice(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      minimumFractionDigits: 2,
      maximumFractionDigits: 8,
    }).format(value);
  } catch {
    return `₹${value}`;
  }
}

function priceSortValue(value: number | null | undefined): number {
  return value == null || !Number.isFinite(value) ? MISSING_SORT_VALUE : value;
}

function dateSortValue(ms: number): number {
  return ms > 0 ? ms : MISSING_SORT_VALUE;
}

/** Accessors for the registry sort hook. Keys match the active catalogue ids. */
export function serviceListSortAccessors(
  columns: readonly ServiceListColumnDef[] = SERVICE_LIST_COLUMNS,
): Record<string, (service: Service) => string | number> {
  const byCell: Record<string, (service: Service) => string | number> = {
    name: (service) => service.name ?? "",
    task: (service) => resolveTaskType(service).toLowerCase(),
    tier: (service) => (service.tierNames ?? service.tiers ?? []).join(", ").toLowerCase(),
    status: (service) => (service.isPublished === true ? 1 : 0),
    createdAt: (service) => dateSortValue(serviceCreatedAtMillis(service)),
    modelName: (service) => serviceModelName(service).toLowerCase(),
    serviceId: (service) => serviceListServiceId(service).toLowerCase(),
    inputPrice: (service) => priceSortValue(service.costPerUnit),
    outputPrice: (service) => priceSortValue(service.outputCostPerUnit),
    cachedInputPrice: (service) => priceSortValue(service.cachedInputCostPerUnit),
    publishedOn: (service) => dateSortValue(servicePublishedOnMillis(service)),
  };
  const accessors: Record<string, (service: Service) => string | number> = {};
  for (const column of columns) {
    if (!SERVICE_SORTABLE_COLUMN_IDS.has(column.id)) continue;
    const accessor = byCell[serviceListCellKey(column.id)];
    if (accessor) accessors[column.id] = accessor;
  }
  return accessors;
}
