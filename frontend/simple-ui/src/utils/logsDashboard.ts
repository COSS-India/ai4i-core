/**
 * Logs Dashboard helpers for AI4IDS-3527 (search / filters / columns).
 * Kept out of the page so the screen stays presentation-focused.
 */

import { INSTITUTION } from "../config/constants";
import type {
  DataTableColumnFilterConfig,
  DataTableColumnFilters,
  DataTableSortState,
} from "../components/common/dataTableTypes";
import type {
  TelemetryTraceColumnDef,
  TelemetryTraceRecord,
  TelemetryTraceSortBy,
} from "../types/observability";

export const AUTO_REFRESH_MS = 37_000;
export const DEFAULT_RANGE_MS = 30 * 60 * 1000;
/** datetime-local is minute precision — treat end as "now" within this window. */
export const LIVE_RANGE_TOLERANCE_MS = 2 * 60 * 1000;

export const KEYWORD_MAX_LENGTH = 256;

export const COLUMN_STORAGE_KEY = "logs-dashboard-columns";

/**
 * Offline fallback matching platform-core COLUMN_DEFINITIONS (AI4IDS-3529).
 * Prefer GET /telemetry/traces/columns when the API is available.
 */
export const FALLBACK_COLUMN_DEFS: TelemetryTraceColumnDef[] = [
  { key: "timestamp", label: "Timestamp", default: true, filterable: false, sortable: true, keyword_searchable: false },
  { key: "status", label: "Status", default: true, filterable: true, sortable: false, keyword_searchable: true },
  { key: "task_type", label: "Task Type", default: true, filterable: true, sortable: false, keyword_searchable: true },
  { key: "url", label: "URL", default: true, filterable: false, sortable: true, keyword_searchable: true },
  { key: "institution", label: INSTITUTION, default: true, filterable: true, sortable: false, keyword_searchable: false },
  { key: "status_code", label: "Status Code", default: false, filterable: true, sortable: true, keyword_searchable: true },
  { key: "error", label: "Error", default: false, filterable: false, sortable: false, keyword_searchable: true },
  { key: "service", label: "Service", default: false, filterable: true, sortable: false, keyword_searchable: true },
  { key: "model", label: "Model", default: false, filterable: false, sortable: false, keyword_searchable: true },
  { key: "latency", label: "Latency (ms)", default: false, filterable: false, sortable: true, keyword_searchable: false },
  { key: "application", label: "Application", default: false, filterable: false, sortable: false, keyword_searchable: true },
  { key: "api_key", label: "API Key", default: false, filterable: false, sortable: false, keyword_searchable: true },
  { key: "end_user", label: "End User", default: false, filterable: true, sortable: false, keyword_searchable: true },
  { key: "metadata", label: "Metadata", default: false, filterable: true, sortable: false, keyword_searchable: true },
  { key: "method", label: "Method", default: false, filterable: false, sortable: false, keyword_searchable: false },
];

export const DEFAULT_COLUMN_KEYS = FALLBACK_COLUMN_DEFS.filter((c) => c.default).map(
  (c) => c.key
);

/** Column keys the search API accepts for `sort_by`. */
export const SORTABLE_API_KEYS: Record<string, TelemetryTraceSortBy> = {
  timestamp: "timestamp",
  url: "url",
  latency: "latency",
  status_code: "status_code",
};

function traceRowField(row: TelemetryTraceRecord, key: string): unknown {
  return Reflect.get(row, key);
}

/** Stable text for client-side sort; avoids `[object Object]` from String(obj). */
function comparableText(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (value == null) return "";
  if (value instanceof Date) return value.toISOString();
  if (Array.isArray(value) || typeof value === "object") {
    try {
      return JSON.stringify(value) ?? "";
    } catch {
      return "";
    }
  }
  return "";
}

function compareTraceRowValues(a: unknown, b: unknown, dir: 1 | -1): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (typeof a === "number" && typeof b === "number") return (a - b) * dir;
  return (
    comparableText(a).localeCompare(comparableText(b), undefined, {
      sensitivity: "base",
    }) * dir
  );
}

/**
 * API sorts the full result set for keys in {@link SORTABLE_API_KEYS};
 * every other column sorts the loaded page only.
 */
export function sortTraceRowsClientSide(
  rows: readonly TelemetryTraceRecord[],
  sort: DataTableSortState,
): TelemetryTraceRecord[] {
  if (SORTABLE_API_KEYS[sort.key]) return [...rows];
  const dir: 1 | -1 = sort.direction === "asc" ? 1 : -1;
  return [...rows].sort((left, right) =>
    compareTraceRowValues(
      traceRowField(left, sort.key),
      traceRowField(right, sort.key),
      dir,
    ),
  );
}

/**
 * Toolbar owns these — no per-column search (same field only once).
 * Method is a column search; Status / Task Type / Institution / time stay on the toolbar.
 */
const TOOLBAR_FILTERED_COLUMN_KEYS = new Set([
  "timestamp",
  "task_type",
  "institution",
  "status",
]);

const MAX_STATUS_CODES = 10;

export const validateStatusCodes = (value: string): string | undefined => {
  const codes = value.split(",").map((c) => c.trim()).filter(Boolean);
  if (codes.length > MAX_STATUS_CODES) {
    return `Up to ${MAX_STATUS_CODES} codes.`;
  }
  const valid = codes.every((c) => /^\d{3}$/.test(c) && Number(c) >= 100 && Number(c) <= 599);
  return valid ? undefined : "Use codes between 100 and 599, comma-separated.";
};

export const parseMetadataPair = (
  value: string,
): { key: string; value: string } | null => {
  const at = value.indexOf("=");
  if (at <= 0) return null;
  const key = value.slice(0, at).trim();
  const val = value.slice(at + 1).trim();
  return key && val ? { key, value: val } : null;
};

const validateMetadataPair = (value: string): string | undefined =>
  parseMetadataPair(value) ? undefined : "Use key=value.";

const containsFilter = (label: string): DataTableColumnFilterConfig => ({
  type: "text",
  placeholder: "Search",
  helper: `${label} contains…`,
});

/**
 * Per-column controls for Logs. Every non-toolbar column gets a search box.
 * Toolbar owns status, time, task type, and institution.
 */
const LOGS_COLUMN_FILTERS: Record<string, DataTableColumnFilterConfig> = {
  end_user: { type: "text", placeholder: "Search", helper: "Exact match on end-user ID" },
  service: { type: "text", placeholder: "Search", helper: "Exact match on service ID" },
  status_code: {
    type: "text",
    placeholder: "Search",
    helper: `Up to ${MAX_STATUS_CODES} codes, comma-separated`,
    validate: validateStatusCodes,
  },
  metadata: {
    type: "text",
    placeholder: "Search",
    helper: "Exact key=value",
    validate: validateMetadataPair,
  },
  url: containsFilter("URL"),
  method: containsFilter("Method"),
  model: containsFilter("Model"),
  application: containsFilter("Application"),
  api_key: containsFilter("API key"),
  error: containsFilter("Error"),
  latency: {
    type: "text",
    placeholder: "Search",
    helper: "Searches the rows on this page only",
  },
};

/**
 * `false` opts the column out of column search (toolbar already filters it).
 * Any other known column gets its config; unknown keys get a plain text search.
 */
export const logsColumnFilterConfig = (
  def: TelemetryTraceColumnDef,
): DataTableColumnFilterConfig | false => {
  if (TOOLBAR_FILTERED_COLUMN_KEYS.has(def.key)) return false;
  return LOGS_COLUMN_FILTERS[def.key] ?? { type: "text", placeholder: "Search" };
};

/** traces/search params for per-column searches; keys follow the column catalogue. */
export type LogsColumnFilterParams = {
  user?: string;
  serviceId?: string;
  statusCode?: string;
  metadataKey?: string;
  metadataValue?: string;
  url?: string;
  method?: string;
  model?: string;
  application?: string;
  apiKey?: string;
  error?: string;
};

export const columnFiltersToTraceParams = (
  filters: DataTableColumnFilters,
): LogsColumnFilterParams => {
  const metadata = filters.metadata ? parseMetadataPair(filters.metadata) : null;
  const statusCode = filters.status_code
    ?.split(",")
    .map((c) => c.trim())
    .filter(Boolean)
    .join(",");
  return {
    user: filters.end_user,
    serviceId: filters.service,
    statusCode: statusCode || undefined,
    metadataKey: metadata?.key,
    metadataValue: metadata?.value,
    url: filters.url,
    method: filters.method,
    model: filters.model,
    application: filters.application,
    apiKey: filters.api_key,
    error: filters.error,
  };
};

/** Error column is admin-only on the screen (parent AC-6 / design). */
export const isAdminOnlyColumnKey = (key: string): boolean => key === "error";

/** Normalise API column labels (e.g. brand Institution). */
export const normalizeColumnDefs = (
  columns: TelemetryTraceColumnDef[]
): TelemetryTraceColumnDef[] =>
  columns.map((col) =>
    col.key === "institution" ? { ...col, label: INSTITUTION } : col
  );

export const formatDateTimeLocal = (date: Date): string => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
};

export const defaultTimeRange = (): { startTime: string; endTime: string } => {
  const now = new Date();
  return {
    endTime: formatDateTimeLocal(now),
    startTime: formatDateTimeLocal(new Date(now.getTime() - DEFAULT_RANGE_MS)),
  };
};

export type LogTimePreset = "custom" | "1h" | "24h" | "7d" | "30d";

export const LOG_TIME_PRESETS: readonly {
  id: Exclude<LogTimePreset, "custom">;
  label: string;
  ms: number;
}[] = [
  { id: "1h", label: "Last 1 hour", ms: 60 * 60 * 1000 },
  { id: "24h", label: "Last 24 hours", ms: 24 * 60 * 60 * 1000 },
  { id: "7d", label: "Last 7 days", ms: 7 * 24 * 60 * 60 * 1000 },
  { id: "30d", label: "Last 30 days", ms: 30 * 24 * 60 * 60 * 1000 },
];

export const rangeForTimePreset = (
  preset: Exclude<LogTimePreset, "custom">,
): { startTime: string; endTime: string } => {
  const ms = LOG_TIME_PRESETS.find((item) => item.id === preset)?.ms ?? DEFAULT_RANGE_MS;
  const now = new Date();
  return {
    endTime: formatDateTimeLocal(now),
    startTime: formatDateTimeLocal(new Date(now.getTime() - ms)),
  };
};

export const convertToISOFormat = (datetimeLocal: string): string => {
  if (!datetimeLocal || datetimeLocal.trim() === "") return "";

  try {
    let normalized = datetimeLocal;
    if (!normalized.includes(":")) return "";

    const colonCount = (normalized.match(/:/g) || []).length;
    if (colonCount === 1) {
      normalized = `${normalized}:00`;
    }

    const date = new Date(normalized);
    if (Number.isNaN(date.getTime())) return "";
    return date.toISOString();
  } catch {
    return "";
  }
};

export const isLiveEndTime = (endTime: string): boolean => {
  if (!endTime.trim()) return true;
  const end = new Date(endTime);
  if (Number.isNaN(end.getTime())) return false;
  return Math.abs(Date.now() - end.getTime()) <= LIVE_RANGE_TOLERANCE_MS;
};

export const isFailureStatus = (status: string): boolean => {
  const s = status.toLowerCase();
  return s === "fail" || s === "failed" || s === "failure" || s === "error";
};

export const isSuccessStatus = (status: string): boolean =>
  status.toLowerCase() === "success";

export const formatMetadataCell = (
  metadata: string[] | string | null | undefined
): string => {
  if (metadata == null || metadata === "") return "—";
  if (Array.isArray(metadata)) {
    return metadata.length ? metadata.join(", ") : "—";
  }
  return String(metadata);
};

/** Earlier FE scaffold used app_id; BE column key is application. */
const LEGACY_COLUMN_KEY_MAP: Record<string, string> = {
  app_id: "application",
};

export const readStoredColumns = (): string[] | null => {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(COLUMN_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed) || !parsed.every((k) => typeof k === "string")) {
      return null;
    }
    return (parsed as string[]).map((k) => LEGACY_COLUMN_KEY_MAP[k] ?? k);
  } catch {
    return null;
  }
};

export const writeStoredColumns = (keys: string[]) => {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(COLUMN_STORAGE_KEY, JSON.stringify(keys));
  } catch {
    // ignore quota / private mode
  }
};

/**
 * Build `columns` query value from the picker selection.
 * Always includes `status_code` for failed-row display; includes `error` for admins (AC-6).
 * Always includes `status` when status_code is requested so the status cell can render.
 */
export const buildColumnsQueryParam = (
  selectedColumns: string[],
  columnOrder: string[],
  options?: { includeError?: boolean }
): string => {
  const keys = new Set(selectedColumns);
  keys.add("status_code");
  keys.add("status");
  if (options?.includeError) {
    keys.add("error");
  }
  const order = [...columnOrder];
  for (const required of ["status", "status_code", "error"] as const) {
    if (keys.has(required) && !order.includes(required)) {
      order.push(required);
    }
  }
  return order.filter((k) => keys.has(k)).join(",");
};
