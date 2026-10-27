/**
 * Service List column catalogue and per-user selection (AI4IDS-3356).
 *
 * `GET /services/columns` (AI4IDS-3565) replaces `SERVICE_LIST_COLUMNS` when
 * that endpoint is available. Browser storage is the fallback for
 * `GET/PUT/DELETE /preferences/columns/service-list` (AI4IDS-3567).
 */

import type { Service } from "../../types/platform";
import { resolveTaskType } from "../../utils/platformService";

export type ServiceListColumnId =
  | "name"
  | "modelTaskType"
  | "tier"
  | "status"
  | "createdAt"
  | "modelName"
  | "serviceId"
  | "inputPrice"
  | "outputPrice"
  | "cachedInputPrice"
  | "publishedOn"
  | "actions";

export type ServiceListColumnFilter = {
  type: string;
  params: string[];
  options: { value: string; label: string }[] | null;
};

export type ServiceListColumnDef = {
  id: string;
  label: string;
  /** Always visible. The picker cannot turn these off. */
  mandatory: boolean;
  /** Shown on the first visit and restored by Reset to default. */
  defaultVisible: boolean;
  sortable?: boolean;
  filterable?: boolean;
  filter?: ServiceListColumnFilter | null;
};

/** Cell renderer key. API ids are snake_case; the offline catalogue is camelCase. */
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

/** Display order. Actions stay last, matching the rest of the admin tables. */
export const SERVICE_LIST_COLUMNS: readonly ServiceListColumnDef[] = [
  { id: "name", label: "Name", mandatory: true, defaultVisible: true },
  { id: "modelTaskType", label: "Model Task Type", mandatory: false, defaultVisible: true },
  { id: "tier", label: "Tier", mandatory: false, defaultVisible: true },
  { id: "status", label: "Status", mandatory: false, defaultVisible: true },
  { id: "createdAt", label: "Created At", mandatory: false, defaultVisible: true },
  { id: "modelName", label: "Model Name", mandatory: false, defaultVisible: false },
  { id: "serviceId", label: "Service ID", mandatory: false, defaultVisible: false },
  { id: "inputPrice", label: "Input Price", mandatory: false, defaultVisible: false },
  { id: "outputPrice", label: "Output Price", mandatory: false, defaultVisible: false },
  { id: "cachedInputPrice", label: "Cached Input Price", mandatory: false, defaultVisible: false },
  { id: "publishedOn", label: "Published On", mandatory: false, defaultVisible: false },
  { id: "actions", label: "Actions", mandatory: true, defaultVisible: true },
];

export const SERVICE_LIST_COLUMN_STORAGE_PREFIX = "service-list-columns";
export const SERVICE_LIST_PREFERENCE_VIEW = "service-list";

/** Missing dates and prices sort after real values when the column is ascending. */
const MISSING_SORT_VALUE = Number.POSITIVE_INFINITY;

export function defaultServiceListColumnIds(
  catalogue: readonly ServiceListColumnDef[] = SERVICE_LIST_COLUMNS,
): string[] {
  return catalogue
    .filter((column) => column.mandatory || column.defaultVisible)
    .map((column) => column.id);
}

/**
 * Keep mandatory columns, drop unknown ids, and restore the default set when
 * nothing besides the mandatory columns would remain.
 * Result is always in catalogue order.
 */
export function resolveServiceListColumns(
  selected: readonly string[] | null | undefined,
  catalogue: readonly ServiceListColumnDef[] = SERVICE_LIST_COLUMNS,
): string[] {
  const defaults = defaultServiceListColumnIds(catalogue);
  const mandatory = new Set(catalogue.filter((column) => column.mandatory).map((column) => column.id));
  const known = new Set(catalogue.map((column) => column.id));
  if (!selected || selected.length === 0) return defaults;

  const picked = new Set(
    selected.filter((id) => known.has(id) && !mandatory.has(id)),
  );
  if (picked.size === 0) return defaults;

  return catalogue
    .filter((column) => column.mandatory || picked.has(column.id))
    .map((column) => column.id);
}

export function canToggleOffServiceListColumn(
  current: readonly string[],
  id: string,
  catalogue: readonly ServiceListColumnDef[] = SERVICE_LIST_COLUMNS,
): boolean {
  const column = catalogue.find((entry) => entry.id === id);
  if (!column || column.mandatory) return false;
  if (!current.includes(id)) return true;
  const mandatory = new Set(catalogue.filter((entry) => entry.mandatory).map((entry) => entry.id));
  const flexibleCount = current.filter((columnId) => !mandatory.has(columnId)).length;
  return flexibleCount > 1;
}

/** Turn a column on or off. Mandatory columns and the last flexible column stay. */
export function toggleServiceListColumn(
  current: readonly string[],
  id: string,
  catalogue: readonly ServiceListColumnDef[] = SERVICE_LIST_COLUMNS,
): string[] {
  if (!canToggleOffServiceListColumn(current, id, catalogue) && current.includes(id)) {
    return resolveServiceListColumns(current, catalogue);
  }
  const next = current.includes(id)
    ? current.filter((columnId) => columnId !== id)
    : [...current, id];
  return resolveServiceListColumns(next, catalogue);
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

function parseFilterOption(
  option: unknown,
): { value: string; label: string } | null {
  if (!option || typeof option !== "object") return null;
  const value = (option as { value?: unknown }).value;
  const label = (option as { label?: unknown }).label;
  if (
    typeof value !== "string" &&
    typeof value !== "number" &&
    typeof value !== "boolean"
  ) {
    return null;
  }
  const text = String(value);
  return {
    value: text,
    label: typeof label === "string" ? label : text,
  };
}

function parseFilterOptions(
  raw: unknown,
): { value: string; label: string }[] | null {
  if (!Array.isArray(raw)) return null;
  const options: { value: string; label: string }[] = [];
  for (const entry of raw) {
    const parsed = parseFilterOption(entry);
    if (parsed) options.push(parsed);
  }
  if (options.length === 0) return null;
  return options;
}

function parseFilterParams(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (param): param is string => typeof param === "string" && param.length > 0,
  );
}

function parseColumnFilter(raw: unknown): ServiceListColumnFilter | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const params = parseFilterParams(row.params);
  if (params.length === 0) return null;
  return {
    type: typeof row.type === "string" ? row.type : "text",
    params,
    options: parseFilterOptions(row.options),
  };
}

function unwrapColumnsPayload(raw: unknown): unknown {
  let data = raw;
  if (data && typeof data === "object" && "data" in data) {
    data = (data as { data: unknown }).data;
  }
  if (data && typeof data === "object" && "columns" in data) {
    data = (data as { columns: unknown }).columns;
  }
  return data;
}

function parseColumnDef(entry: unknown): ServiceListColumnDef | null {
  if (!entry || typeof entry !== "object") return null;
  const row = entry as Record<string, unknown>;
  if (typeof row.id !== "string" || !row.id) return null;
  if (typeof row.label !== "string" || !row.label) return null;
  const filter = parseColumnFilter(row.filter);
  const mandatory = row.mandatory === true;
  return {
    id: row.id,
    label: row.label,
    mandatory,
    defaultVisible: mandatory || row.defaultVisible === true,
    sortable: row.sortable === true,
    filterable: row.filterable === true && Boolean(filter),
    filter,
  };
}

/** Parse `GET /services/columns`. Returns null when the body is not that contract. */
export function parseServiceListColumnsPayload(raw: unknown): ServiceListColumnDef[] | null {
  const data = unwrapColumnsPayload(raw);
  if (!Array.isArray(data)) return null;
  const columns: ServiceListColumnDef[] = [];
  for (const entry of data) {
    const column = parseColumnDef(entry);
    if (column) columns.push(column);
  }
  if (columns.length === 0) return null;
  return columns;
}

/** Preference body from GET/PUT/DELETE `/preferences/columns/service-list`. */
export type ServiceColumnPreference = {
  visibleColumns: string[];
  /** True when nothing is saved for this user (role defaults). */
  isDefault: boolean;
  viewKey?: string;
};

/** Parse `GET /preferences/columns/service-list`. */
export function parseVisibleColumnsPayload(raw: unknown): string[] | null {
  return parseServiceColumnPreferencePayload(raw)?.visibleColumns ?? null;
}

/**
 * Parse preference payloads. GET always returns 200 with this shape (never 404).
 * `isDefault` means nothing saved — not “selection equals the defaults”.
 */
export function parseServiceColumnPreferencePayload(
  raw: unknown,
): ServiceColumnPreference | null {
  let data = raw;
  if (data && typeof data === "object" && "data" in data) {
    data = (data as { data: unknown }).data;
  }

  let list: unknown[] | null = null;
  let isDefault = false;
  let viewKey: string | undefined;
  if (Array.isArray(data)) {
    list = data;
  } else if (data && typeof data === "object") {
    const row = data as {
      visibleColumns?: unknown;
      isDefault?: unknown;
      viewKey?: unknown;
    };
    if (Array.isArray(row.visibleColumns)) list = row.visibleColumns;
    if (row.isDefault === true) isDefault = true;
    if (typeof row.viewKey === "string") viewKey = row.viewKey;
  }

  if (!list) return null;
  return {
    visibleColumns: list.filter((id): id is string => typeof id === "string"),
    isDefault,
    viewKey,
  };
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

export function serviceCreatedAtMillis(service: Service): number {
  const raw = service.createdAt ?? service.created_at;
  if (!raw) return 0;
  const ms = Date.parse(raw);
  return Number.isNaN(ms) ? 0 : ms;
}

export function servicePublishedOnMillis(service: Service): number {
  // List API emits ISO `publishedAt`; `publishedOn` is only set by the local
  // publish/unpublish optimistic patch in this tab.
  const iso = service.publishedAt;
  if (typeof iso === "string" && iso.trim()) {
    const ms = Date.parse(iso);
    if (!Number.isNaN(ms)) return ms;
  }
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
    if (column.sortable === false) continue;
    const accessor = byCell[serviceListCellKey(column.id)];
    if (accessor) accessors[column.id] = accessor;
  }
  return accessors;
}
