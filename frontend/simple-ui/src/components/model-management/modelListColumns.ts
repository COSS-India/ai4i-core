/**
 * Model List column catalogue + local preference helpers (AI4IDS-3351).
 * Mirrors the Service List pattern (AI4IDS-3356). FE catalogue is the source of
 * truth; column visibility is browser-local for 2.11 (server prefs follow-up).
 */

export type ModelListColumnId =
  | "name"
  | "version"
  | "task"
  | "provider"
  | "status"
  | "created"
  | "serviceCount"
  | "actions";

export type ModelListColumnDef = {
  /** Known ids are ModelListColumnId; string allows a future API catalogue. */
  id: string;
  label: string;
  mandatory: boolean;
  defaultVisible: boolean;
};

/**
 * Display order. Mandatory set from AI4IDS-3351 (+ Actions, same as services).
 * Provider maps to submitter.name until BE exposes a dedicated field.
 */
export const MODEL_LIST_COLUMNS: readonly ModelListColumnDef[] = [
  { id: "name", label: "Name", mandatory: true, defaultVisible: true },
  { id: "version", label: "Version", mandatory: true, defaultVisible: true },
  { id: "task", label: "Task Type", mandatory: true, defaultVisible: true },
  { id: "provider", label: "Provider Name", mandatory: true, defaultVisible: true },
  { id: "status", label: "Status", mandatory: false, defaultVisible: true },
  { id: "created", label: "Created At", mandatory: false, defaultVisible: true },
  {
    id: "serviceCount",
    label: "No. of Services",
    mandatory: false,
    defaultVisible: true,
  },
  { id: "actions", label: "Actions", mandatory: true, defaultVisible: true },
];

export const MODEL_LIST_COLUMN_STORAGE_PREFIX = "model-list-columns";

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
