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
 * Display order. Mandatory columns match the config's `required` flags.
 * `defaultVisible` is the first-visit and "Reset to default" set.
 */
export const MODEL_LIST_COLUMNS: readonly ModelListColumnDef[] = [
  { id: "name", label: "Name", mandatory: true, defaultVisible: true },
  { id: "version", label: "Version", mandatory: false, defaultVisible: true },
  { id: "taskType", label: "Task Type", mandatory: false, defaultVisible: true },
  { id: "providerName", label: "Provider Name", mandatory: false, defaultVisible: true },
  { id: "status", label: "Status", mandatory: false, defaultVisible: false },
  { id: "createdAt", label: "Created At", mandatory: false, defaultVisible: false },
  {
    id: "noOfServices",
    label: "No. of Services",
    mandatory: false,
    defaultVisible: false,
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

const BUILT_IN_MODEL_LIST_COLUMNS = new Map(
  MODEL_LIST_COLUMNS.map((column) => [column.id, column]),
);

const ACTIONS_COLUMN = MODEL_LIST_COLUMNS.find((column) => column.id === "actions");

/**
 * Catalogue from `model-column` config entries. Keys the table cannot render are
 * dropped; an empty result falls back to MODEL_LIST_COLUMNS. The config sets
 * order, labels and which columns are mandatory (`required`). A column is
 * visible by default when it is mandatory or the entry's `defaultVisible` says
 * so; without that flag the built-in default applies. Actions (the Deprecate /
 * Activate switches) is appended, as mandatory, if left out.
 */
export function modelListColumnsFromConfig(
  entries:
    | readonly { key: string; label: string; required: boolean; defaultVisible?: boolean }[]
    | null
    | undefined,
): readonly ModelListColumnDef[] {
  const catalogue: ModelListColumnDef[] = [];
  for (const entry of entries ?? []) {
    const builtIn = BUILT_IN_MODEL_LIST_COLUMNS.get(entry.key);
    if (builtIn == null) continue;
    if (catalogue.some((column) => column.id === entry.key)) continue;
    catalogue.push({
      id: entry.key,
      label: entry.label,
      mandatory: entry.required,
      defaultVisible: entry.defaultVisible ?? builtIn.defaultVisible,
    });
  }
  if (catalogue.length === 0) return MODEL_LIST_COLUMNS;
  if (ACTIONS_COLUMN && !catalogue.some((column) => column.id === ACTIONS_COLUMN.id)) {
    catalogue.push(ACTIONS_COLUMN);
  }
  return catalogue;
}

export function defaultModelListColumnIds(
  catalogue: readonly ModelListColumnDef[] = MODEL_LIST_COLUMNS,
): string[] {
  return catalogue
    .filter((column) => column.mandatory || column.defaultVisible)
    .map((column) => column.id);
}

/**
 * Keep mandatory columns and drop unknown ids. Optional columns may all be
 * hidden; defaults apply only when nothing usable is stored (first visit, or
 * every stored id is gone from the catalogue). Result is catalogue order.
 */
export function resolveModelListColumns(
  selected: readonly string[] | null | undefined,
  catalogue: readonly ModelListColumnDef[] = MODEL_LIST_COLUMNS,
): string[] {
  const known = new Set(catalogue.map((column) => column.id));
  const picked = new Set((selected ?? []).filter((id) => known.has(id)));
  if (picked.size === 0) return defaultModelListColumnIds(catalogue);
  return catalogue
    .filter((column) => column.mandatory || picked.has(column.id))
    .map((column) => column.id);
}

/** Only mandatory columns are locked; every optional column can be turned off. */
export function canToggleOffModelListColumn(
  _current: readonly string[],
  id: string,
  catalogue: readonly ModelListColumnDef[] = MODEL_LIST_COLUMNS,
): boolean {
  const column = catalogue.find((entry) => entry.id === id);
  return column != null && !column.mandatory;
}

/** Turn an optional column on or off. Mandatory columns stay. */
export function toggleModelListColumn(
  current: readonly string[],
  id: string,
  catalogue: readonly ModelListColumnDef[] = MODEL_LIST_COLUMNS,
): string[] {
  if (!canToggleOffModelListColumn(current, id, catalogue)) {
    return resolveModelListColumns(current, catalogue);
  }
  const next = current.includes(id)
    ? current.filter((columnId) => columnId !== id)
    : [...current, id];
  return resolveModelListColumns(next, catalogue);
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
