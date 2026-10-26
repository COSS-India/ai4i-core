/**
 * Logs Dashboard helpers for AI4IDS-3527 (search / filters / columns).
 * Kept out of the page so the screen stays presentation-focused.
 */

import { INSTITUTION } from "../config/constants";
import { FIELD_HINTS } from "../config/fieldHints";
import type {
  TelemetryTraceColumnDef,
  TelemetryTraceSortBy,
} from "../types/observability";

export const AUTO_REFRESH_MS = 37_000;
export const DEFAULT_RANGE_MS = 30 * 60 * 1000;
/** datetime-local is minute precision — treat end as "now" within this window. */
export const LIVE_RANGE_TOLERANCE_MS = 2 * 60 * 1000;

export const END_USER_MAX_LENGTH = 256;
export const KEYWORD_MAX_LENGTH = 256;
export const METADATA_KEY_MAX_LENGTH = 64;
export const METADATA_VALUE_MAX_LENGTH = 512;
export const STATUS_CODE_MAX_COUNT = 10;

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

export const parseMetadataFilter = (
  raw: string
): { key: string; value: string } | { error: string } | null => {
  const text = raw.trim();
  if (!text) return null;
  const hints = FIELD_HINTS.logs.metadata;
  const separator = text.indexOf("=");
  if (separator === -1) return { error: hints.missingSeparator };
  const key = text.slice(0, separator).trim();
  const value = text.slice(separator + 1).trim();
  if (!key) return { error: hints.missingKey };
  if (!value) return { error: hints.missingValue };
  if (key.length > METADATA_KEY_MAX_LENGTH) return { error: hints.keyTooLong };
  if (value.length > METADATA_VALUE_MAX_LENGTH) return { error: hints.valueTooLong };
  return { key, value };
};

export const parseStatusCodeFilter = (
  raw: string
): { value: string } | { error: string } | null => {
  const text = raw.trim();
  if (!text) return null;
  const parts = text.split(",").map((p) => p.trim()).filter(Boolean);
  if (parts.length === 0) return null;
  if (parts.length > STATUS_CODE_MAX_COUNT) {
    return { error: FIELD_HINTS.logs.statusCode.invalid };
  }
  for (const part of parts) {
    if (!/^\d{3}$/.test(part)) {
      return { error: FIELD_HINTS.logs.statusCode.invalid };
    }
    const code = Number(part);
    if (code < 100 || code > 599) {
      return { error: FIELD_HINTS.logs.statusCode.invalid };
    }
  }
  return { value: parts.join(",") };
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
