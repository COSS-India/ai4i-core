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

/** Contract fallback when GET /telemetry/traces/columns is not deployed yet. */
export const FALLBACK_COLUMN_DEFS: TelemetryTraceColumnDef[] = [
  { key: "timestamp", label: "Timestamp", default: true, filter: "date_range", keyword: false, sort: true, admin_only: false },
  { key: "status", label: "Status", default: true, filter: "status", keyword: true, sort: false, admin_only: false },
  { key: "task_type", label: "Task Type", default: true, filter: "task_type", keyword: true, sort: false, admin_only: false },
  { key: "url", label: "URL", default: true, filter: null, keyword: true, sort: true, admin_only: false },
  { key: "institution", label: INSTITUTION, default: true, filter: "institution", keyword: false, sort: false, admin_only: false },
  { key: "status_code", label: "Status Code", default: false, filter: "status_code", keyword: true, sort: true, admin_only: false },
  { key: "error", label: "Error", default: false, filter: null, keyword: true, sort: false, admin_only: true },
  { key: "service", label: "Service", default: false, filter: "service", keyword: true, sort: false, admin_only: false },
  { key: "model", label: "Model", default: false, filter: null, keyword: true, sort: false, admin_only: false },
  { key: "latency", label: "Latency (ms)", default: false, filter: null, keyword: false, sort: true, admin_only: false },
  { key: "app_id", label: "Application", default: false, filter: null, keyword: true, sort: false, admin_only: false },
  { key: "api_key", label: "API Key", default: false, filter: null, keyword: true, sort: false, admin_only: false },
  { key: "end_user", label: "End User", default: false, filter: "user", keyword: true, sort: false, admin_only: false },
  { key: "metadata", label: "Metadata", default: false, filter: "metadata", keyword: true, sort: false, admin_only: false },
  { key: "method", label: "Method", default: false, filter: null, keyword: false, sort: false, admin_only: false },
];

export const DEFAULT_COLUMN_KEYS = FALLBACK_COLUMN_DEFS.filter((c) => c.default).map(
  (c) => c.key
);

export const SORTABLE_API_KEYS: Record<string, TelemetryTraceSortBy> = {
  timestamp: "timestamp",
  url: "url",
  latency: "latency",
  status_code: "status_code",
};

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
  return s === "fail" || s === "failure" || s === "error";
};

export const isSuccessStatus = (status: string): boolean =>
  status.toLowerCase() === "success";

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

export const readStoredColumns = (): string[] | null => {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(COLUMN_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed) || !parsed.every((k) => typeof k === "string")) {
      return null;
    }
    return parsed as string[];
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
 * Build `columns` query value: visible keys + status_code for failed-row display.
 * When `includeError` is set (admins), always request `error` so AC-6 can show it
 * on failed rows without requiring the Error column to be selected.
 */
export const buildColumnsQueryParam = (
  selectedColumns: string[],
  columnOrder: string[],
  options?: { includeError?: boolean }
): string => {
  const keys = new Set(selectedColumns);
  keys.add("status_code");
  if (options?.includeError) {
    keys.add("error");
  }
  const order = [...columnOrder];
  if (!order.includes("status_code")) order.push("status_code");
  if (options?.includeError && !order.includes("error")) order.push("error");
  return order.filter((k) => keys.has(k)).join(",");
};
