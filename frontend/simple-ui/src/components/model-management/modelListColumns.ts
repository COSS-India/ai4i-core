/**
 * Model List column catalogue + local preference helpers (AI4IDS-3351).
 * Mirrors the Service List pattern (AI4IDS-3356). The `model-column` config is
 * the source of truth for order, labels and required columns; MODEL_LIST_COLUMNS
 * is the fallback. Ids match the config keys (and `GET /models/list?columns=`).
 * Column visibility is browser-local for 2.11 (server prefs follow-up).
 */

export type ModelListColumnId =
  | "name"
  | "version"
  | "taskType"
  | "providerName"
  | "status"
  | "createdAt"
  | "noOfServices"
  | "actions";

export type ModelListColumnDef = {
  /** Known ids are ModelListColumnId; string allows a config-driven catalogue. */
  id: string;
  label: string;
  mandatory: boolean;
  defaultVisible: boolean;
};

/**
 * Fallback when the `model-column` config is missing or fails to load.
 * Display order. Mandatory set from AI4IDS-3351 (+ Actions, same as services).
 */
export const MODEL_LIST_COLUMNS: readonly ModelListColumnDef[] = [
  { id: "name", label: "Name", mandatory: true, defaultVisible: true },
  { id: "version", label: "Version", mandatory: true, defaultVisible: true },
  { id: "taskType", label: "Task Type", mandatory: true, defaultVisible: true },
  { id: "providerName", label: "Provider Name", mandatory: true, defaultVisible: true },
  { id: "status", label: "Status", mandatory: false, defaultVisible: true },
  { id: "createdAt", label: "Created At", mandatory: false, defaultVisible: true },
  {
    id: "noOfServices",
    label: "No. of Services",
    mandatory: false,
    defaultVisible: true,
  },
  { id: "actions", label: "Actions", mandatory: true, defaultVisible: true },
];

export const MODEL_LIST_COLUMN_STORAGE_PREFIX = "model-list-columns";

/**
 * Always requested from GET /models/list, visible or not. Search, sort and the
 * Status / Task Type filters run on the server, so they need no row fields.
 * - `actions`: the API returns `modelId`, `name` and `versionStatus` for it,
 *   which the action switches and their toasts read.
 * - `version`: Deprecate / Activate send it, and `actions` does not include it.
 */
const MODEL_LIST_ALWAYS_FETCHED_COLUMN_IDS: readonly ModelListColumnId[] = [
  "version",
  "actions",
];

/** `columns=` value for GET /models/list: the visible ids plus the always-fetched ones. */
export function modelListColumnsParam(visibleIds: readonly string[]): string {
  const ids = new Set(visibleIds);
  for (const id of MODEL_LIST_ALWAYS_FETCHED_COLUMN_IDS) ids.add(id);
  return Array.from(ids).join(",");
}

const KNOWN_MODEL_LIST_COLUMN_IDS = new Set(MODEL_LIST_COLUMNS.map((column) => column.id));

/**
 * Catalogue from `model-column` config entries. Keys the table cannot render are
 * dropped; an empty result falls back to MODEL_LIST_COLUMNS.
 */
export function modelListColumnsFromConfig(
  entries: readonly { key: string; label: string; required: boolean }[] | null | undefined,
): readonly ModelListColumnDef[] {
  const catalogue: ModelListColumnDef[] = [];
  for (const entry of entries ?? []) {
    if (!KNOWN_MODEL_LIST_COLUMN_IDS.has(entry.key)) continue;
    if (catalogue.some((column) => column.id === entry.key)) continue;
    catalogue.push({
      id: entry.key,
      label: entry.label,
      mandatory: entry.required,
      defaultVisible: true,
    });
  }
  return catalogue.length > 0 ? catalogue : MODEL_LIST_COLUMNS;
}

export function defaultModelListColumnIds(
  catalogue: readonly ModelListColumnDef[] = MODEL_LIST_COLUMNS,
): string[] {
  return catalogue
    .filter((column) => column.mandatory || column.defaultVisible)
    .map((column) => column.id);
}

/**
 * Keep mandatory columns, drop unknown ids, and restore defaults when nothing
 * besides the mandatory columns would remain. Result is catalogue order.
 */
export function resolveModelListColumns(
  selected: readonly string[] | null | undefined,
  catalogue: readonly ModelListColumnDef[] = MODEL_LIST_COLUMNS,
): string[] {
  const defaults = defaultModelListColumnIds(catalogue);
  const mandatory = new Set(
    catalogue.filter((column) => column.mandatory).map((column) => column.id),
  );
  const known = new Set(catalogue.map((column) => column.id));
  if (selected && selected.length > 0) {
    const picked = new Set(
      selected.filter((id) => known.has(id) && !mandatory.has(id)),
    );
    if (picked.size > 0) {
      return catalogue
        .filter((column) => column.mandatory || picked.has(column.id))
        .map((column) => column.id);
    }
  }
  return defaults;
}

export function canToggleOffModelListColumn(
  current: readonly string[],
  id: string,
  catalogue: readonly ModelListColumnDef[] = MODEL_LIST_COLUMNS,
): boolean {
  const column = catalogue.find((entry) => entry.id === id);
  if (column == null || column.mandatory) return false;
  if (current.includes(id) === false) return true;
  const mandatory = new Set(
    catalogue.filter((entry) => entry.mandatory).map((entry) => entry.id),
  );
  const flexibleCount = current.filter((columnId) => !mandatory.has(columnId)).length;
  return flexibleCount > 1;
}

/** Turn a column on or off. Mandatory columns and the last flexible column stay. */
export function toggleModelListColumn(
  current: readonly string[],
  id: string,
  catalogue: readonly ModelListColumnDef[] = MODEL_LIST_COLUMNS,
): string[] {
  const isVisible = current.includes(id);
  if (isVisible) {
    if (canToggleOffModelListColumn(current, id, catalogue)) {
      return resolveModelListColumns(
        current.filter((columnId) => columnId !== id),
        catalogue,
      );
    }
    return resolveModelListColumns(current, catalogue);
  }
  return resolveModelListColumns([...current, id], catalogue);
}

export type ModelListColumnPreferenceStore = {
  read: (userId: string) => string[] | null;
  write: (userId: string, columnIds: readonly string[]) => void;
};

export function modelListColumnStorageKey(userId: string): string {
  return `${MODEL_LIST_COLUMN_STORAGE_PREFIX}:${userId}`;
}

export const browserModelListColumnStore: ModelListColumnPreferenceStore = {
  read(userId) {
    if (globalThis.window === undefined || !userId) return null;
    try {
      const raw = globalThis.window.localStorage.getItem(
        modelListColumnStorageKey(userId),
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
        modelListColumnStorageKey(userId),
        JSON.stringify(columnIds),
      );
    } catch {
      // Private mode or a full quota: the selection still applies for this visit.
    }
  },
};

export function loadModelListColumns(
  userId: string,
  store: ModelListColumnPreferenceStore = browserModelListColumnStore,
  catalogue: readonly ModelListColumnDef[] = MODEL_LIST_COLUMNS,
): string[] {
  if (userId) {
    return resolveModelListColumns(store.read(userId), catalogue);
  }
  return defaultModelListColumnIds(catalogue);
}

export function saveModelListColumns(
  userId: string,
  columnIds: readonly string[],
  store: ModelListColumnPreferenceStore = browserModelListColumnStore,
  catalogue: readonly ModelListColumnDef[] = MODEL_LIST_COLUMNS,
): string[] {
  const resolved = resolveModelListColumns(columnIds, catalogue);
  if (userId) store.write(userId, resolved);
  return resolved;
}
