/**
 * Service List column catalogue and per-user selection (AI4IDS-3356).
 *
 * The catalogue is the frontend stand-in for the columns-metadata API
 * (AI4IDS-3565). `ServiceListColumnPreferenceStore` is the stand-in for
 * server-side preference storage (AI4IDS-3567): swap the store without
 * changing the table.
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

export type ServiceListColumnDef = {
  id: ServiceListColumnId;
  label: string;
  /** Always visible. The picker cannot turn these off. */
  mandatory: boolean;
  /** Shown on the first visit and restored by Reset to default. */
  defaultVisible: boolean;
};

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

const COLUMN_IDS = new Set<string>(SERVICE_LIST_COLUMNS.map((column) => column.id));

const MANDATORY_IDS = SERVICE_LIST_COLUMNS.filter((column) => column.mandatory).map(
  (column) => column.id,
);

export const SERVICE_LIST_COLUMN_STORAGE_PREFIX = "service-list-columns";

/** Missing dates and prices sort after real values when the column is ascending. */
const MISSING_SORT_VALUE = Number.POSITIVE_INFINITY;

export function defaultServiceListColumnIds(): ServiceListColumnId[] {
  return SERVICE_LIST_COLUMNS.filter(
    (column) => column.mandatory || column.defaultVisible,
  ).map((column) => column.id);
}

export function isServiceListColumnId(value: string): value is ServiceListColumnId {
  return COLUMN_IDS.has(value);
}

/**
 * Keep mandatory columns, drop unknown ids, and restore the default set when
 * nothing besides the mandatory columns would remain.
 * Result is always in catalogue order.
 */
export function resolveServiceListColumns(
  selected: readonly string[] | null | undefined,
): ServiceListColumnId[] {
  const defaults = defaultServiceListColumnIds();
  if (!selected || selected.length === 0) return defaults;

  const picked = new Set(
    selected.filter(
      (id): id is ServiceListColumnId =>
        isServiceListColumnId(id) && !MANDATORY_IDS.includes(id),
    ),
  );
  if (picked.size === 0) return defaults;

  return SERVICE_LIST_COLUMNS.filter(
    (column) => column.mandatory || picked.has(column.id),
  ).map((column) => column.id);
}

export function canToggleOffServiceListColumn(
  current: readonly ServiceListColumnId[],
  id: ServiceListColumnId,
): boolean {
  const column = SERVICE_LIST_COLUMNS.find((entry) => entry.id === id);
  if (!column || column.mandatory) return false;
  if (!current.includes(id)) return true;
  const flexibleCount = current.filter(
    (columnId) => !MANDATORY_IDS.includes(columnId),
  ).length;
  return flexibleCount > 1;
}

/** Turn a column on or off. Mandatory columns and the last flexible column stay. */
export function toggleServiceListColumn(
  current: readonly ServiceListColumnId[],
  id: ServiceListColumnId,
): ServiceListColumnId[] {
  if (!canToggleOffServiceListColumn(current, id) && current.includes(id)) {
    return resolveServiceListColumns(current);
  }
  const next = current.includes(id)
    ? current.filter((columnId) => columnId !== id)
    : [...current, id];
  return resolveServiceListColumns(next);
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
    if (typeof window === "undefined" || !userId) return null;
    try {
      const raw = window.localStorage.getItem(serviceListColumnStorageKey(userId));
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed) || !parsed.every((id) => typeof id === "string")) {
        return null;
      }
      return parsed as string[];
    } catch {
      return null;
    }
  },
  write(userId, columnIds) {
    if (typeof window === "undefined" || !userId) return;
    try {
      window.localStorage.setItem(
        serviceListColumnStorageKey(userId),
        JSON.stringify(columnIds),
      );
    } catch {
      // Private mode or a full quota: the selection still applies for this visit.
    }
  },
};

export function loadServiceListColumns(
  userId: string,
  store: ServiceListColumnPreferenceStore = browserServiceListColumnStore,
): ServiceListColumnId[] {
  if (!userId) return defaultServiceListColumnIds();
  return resolveServiceListColumns(store.read(userId));
}

export function saveServiceListColumns(
  userId: string,
  columnIds: readonly string[],
  store: ServiceListColumnPreferenceStore = browserServiceListColumnStore,
): ServiceListColumnId[] {
  const resolved = resolveServiceListColumns(columnIds);
  if (userId) store.write(userId, resolved);
  return resolved;
}

export function serviceCreatedAtMillis(service: Service): number {
  const raw = service.createdAt ?? service.created_at;
  if (!raw) return 0;
  const ms = Date.parse(raw);
  return Number.isNaN(ms) ? 0 : ms;
}

export function servicePublishedOnMillis(service: Service): number {
  const raw = service.publishedOn;
  if (raw == null || !Number.isFinite(raw) || raw <= 0) return 0;
  return raw < 1e12 ? raw * 1000 : raw;
}

export function serviceModelName(service: Service): string {
  return service.model?.name || service.modelName || "";
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
      maximumFractionDigits: 6,
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

/** Accessors for the registry sort hook. Keys match column ids. */
export function serviceListSortAccessors(): Record<string, (service: Service) => string | number> {
  return {
    name: (service) => service.name ?? "",
    modelTaskType: (service) => resolveTaskType(service).toLowerCase(),
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
}
