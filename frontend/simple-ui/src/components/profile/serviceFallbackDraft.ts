/**
 * Draft model for an Application's service fallbacks (AI4IDS-3488).
 *
 * The API stores `{ primary: [fallback, ...] }`. The editor shows one row per
 * primary: primary → fallback, with the task type taken from the primary.
 * Phase 1 edits one fallback per primary; any further fallbacks saved through
 * the API ride along unchanged.
 */
import type { ServiceFallbackMap } from "../../types/application";
import type { Service } from "../../types/platform";

export interface FallbackServiceOption {
  serviceId: string;
  name: string;
  modelId: string;
  /** Lower-case, e.g. "nmt". */
  taskType: string;
}

export interface FallbackCatalogue {
  byId: Map<string, FallbackServiceOption>;
  /** Task type → its services, sorted by name. */
  byTask: Map<string, FallbackServiceOption[]>;
}

export interface FallbackRow {
  key: string;
  /** The primary's task type; limits the fallback options. */
  taskType: string;
  primaryId: string;
  fallbackId: string;
  /** Fallbacks after the first, saved through the API. Kept as-is on save. */
  extraFallbackIds: string[];
  /** Saved primary this row was loaded from; "" for a row added in this session. */
  originalPrimaryId: string;
}

export type ModelMatch = "same" | "different" | null;

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function toFallbackServiceOption(service: Service): FallbackServiceOption | null {
  const serviceId = text(service.serviceId) || text(service.service_id);
  const task = service.task as { type?: unknown } | undefined;
  const taskType = (
    text((service as { taskType?: unknown }).taskType) ||
    text(task?.type) ||
    text(service.task_type)
  ).toLowerCase();
  if (!serviceId || !taskType) return null;
  return {
    serviceId,
    name: text(service.name) || serviceId,
    modelId: text(service.modelId) || text(service.model_id),
    taskType,
  };
}

function byName(a: FallbackServiceOption, b: FallbackServiceOption): number {
  return a.name.localeCompare(b.name);
}

export function buildFallbackCatalogue(services: Service[]): FallbackCatalogue {
  const byId = new Map<string, FallbackServiceOption>();
  for (const service of services) {
    const option = toFallbackServiceOption(service);
    if (option) byId.set(option.serviceId, option);
  }
  const byTask = new Map<string, FallbackServiceOption[]>();
  for (const option of Array.from(byId.values())) {
    const list = byTask.get(option.taskType) ?? [];
    list.push(option);
    byTask.set(option.taskType, list);
  }
  byTask.forEach((list) => {
    list.sort(byName);
  });
  return { byId, byTask };
}

let rowSeq = 0;
function nextRowKey(): string {
  rowSeq += 1;
  return `fallback-${rowSeq}`;
}

export function emptyFallbackRow(): FallbackRow {
  return {
    key: nextRowKey(),
    taskType: "",
    primaryId: "",
    fallbackId: "",
    extraFallbackIds: [],
    originalPrimaryId: "",
  };
}

export function rowsFromFallbackMap(
  map: ServiceFallbackMap,
  catalogue: FallbackCatalogue,
): FallbackRow[] {
  return Object.entries(map)
    .filter(([, fallbacks]) => fallbacks.length > 0)
    .map(([primaryId, [fallbackId, ...extraFallbackIds]]) => ({
      key: nextRowKey(),
      taskType:
        catalogue.byId.get(primaryId)?.taskType ?? catalogue.byId.get(fallbackId)?.taskType ?? "",
      primaryId,
      fallbackId,
      extraFallbackIds,
      originalPrimaryId: primaryId,
    }));
}

/** After a save, the current rows become the saved baseline. */
export function markRowsSaved(rows: FallbackRow[]): FallbackRow[] {
  return rows.map((row) => ({ ...row, originalPrimaryId: row.primaryId }));
}

function rowFallbackIds(row: FallbackRow): string[] {
  return fallbackMapFromRows([row])[row.primaryId] ?? [];
}

/**
 * Unsaved changes, one per fallback: each added or edited row, plus each
 * saved fallback that was removed. A row edited back to its saved value
 * does not count.
 */
export function countFallbackChanges(saved: ServiceFallbackMap, rows: FallbackRow[]): number {
  let changes = 0;
  for (const row of rows) {
    if (!row.originalPrimaryId || !isRowComplete(row)) {
      changes += 1;
      continue;
    }
    const before = saved[row.originalPrimaryId] ?? [];
    const after = rowFallbackIds(row);
    const same =
      row.primaryId === row.originalPrimaryId &&
      before.length === after.length &&
      before.every((id, index) => id === after[index]);
    if (!same) changes += 1;
  }
  const kept = new Set(rows.map((row) => row.originalPrimaryId).filter(Boolean));
  changes += Object.keys(saved).filter((primary) => !kept.has(primary)).length;
  return changes;
}

export function isRowComplete(row: FallbackRow): boolean {
  return Boolean(row.taskType && row.primaryId && row.fallbackId);
}

/** A saved id that is no longer published in the Tier. The backend no longer uses such a fallback. */
export function isRowStale(row: FallbackRow, catalogue: FallbackCatalogue): boolean {
  return [row.primaryId, row.fallbackId, ...row.extraFallbackIds].some(
    (id) => Boolean(id) && !catalogue.byId.has(id),
  );
}

/** Complete rows only, in the shape PATCH expects. */
export function fallbackMapFromRows(rows: FallbackRow[]): ServiceFallbackMap {
  const map: ServiceFallbackMap = {};
  for (const row of rows) {
    if (!isRowComplete(row)) continue;
    map[row.primaryId] = [row.fallbackId, ...extraFallbacksFor(row)];
  }
  return map;
}

/** The row's fallbacks after the first, as they are shown and saved. */
export function extraFallbacksFor(row: FallbackRow): string[] {
  return row.extraFallbackIds.filter((id) => id !== row.fallbackId && id !== row.primaryId);
}

/**
 * Drops rows whose primary or fallback is no longer in the Tier, and only the
 * unavailable extra fallbacks from the rest.
 */
export function withoutStaleServices(
  rows: FallbackRow[],
  catalogue: FallbackCatalogue,
): FallbackRow[] {
  const gone = (id: string) => Boolean(id) && !catalogue.byId.has(id);
  return rows
    .filter((row) => !gone(row.primaryId) && !gone(row.fallbackId))
    .map((row) => ({ ...row, extraFallbackIds: row.extraFallbackIds.filter((id) => !gone(id)) }));
}

function primariesUsedElsewhere(rows: FallbackRow[], rowKey: string): Set<string> {
  return new Set(rows.filter((r) => r.key !== rowKey && r.primaryId).map((r) => r.primaryId));
}

/**
 * Services with at least one other service of the same task type in the Tier,
 * that no other row already uses as its primary.
 */
export function primaryOptionsFor(
  row: FallbackRow,
  rows: FallbackRow[],
  catalogue: FallbackCatalogue,
): FallbackServiceOption[] {
  const used = primariesUsedElsewhere(rows, row.key);
  const options = Array.from(catalogue.byTask.values())
    .filter((list) => list.length >= 2)
    .flat()
    .filter((o) => !used.has(o.serviceId));
  options.sort(byName);
  return options;
}

/** Same task type as the primary, never the primary itself. */
export function fallbackOptionsFor(
  row: FallbackRow,
  catalogue: FallbackCatalogue,
): FallbackServiceOption[] {
  return (catalogue.byTask.get(row.taskType) ?? []).filter((o) => o.serviceId !== row.primaryId);
}

/** Whether a new row would have any primary to choose from. */
export function canAddFallbackRow(rows: FallbackRow[], catalogue: FallbackCatalogue): boolean {
  return primaryOptionsFor(emptyFallbackRow(), rows, catalogue).length > 0;
}

/** True when no task type in the Tier has a second service to fall back to. */
export function tierHasNoAlternatives(catalogue: FallbackCatalogue): boolean {
  return Array.from(catalogue.byTask.values()).every((list) => list.length < 2);
}

export function modelMatchFor(row: FallbackRow, catalogue: FallbackCatalogue): ModelMatch {
  const primary = catalogue.byId.get(row.primaryId);
  const fallback = catalogue.byId.get(row.fallbackId);
  if (!primary || !fallback) return null;
  return primary.modelId && primary.modelId === fallback.modelId ? "same" : "different";
}

/** Takes the task type from the primary; a fallback of another task type is cleared. */
export function withPrimary(
  row: FallbackRow,
  primaryId: string,
  catalogue: FallbackCatalogue,
): FallbackRow {
  if (row.primaryId === primaryId) return row;
  const taskType = catalogue.byId.get(primaryId)?.taskType ?? "";
  // Fallbacks of another task type cannot serve the new primary, so they go with it.
  const sameTask = taskType === row.taskType;
  return {
    ...row,
    taskType,
    primaryId,
    fallbackId: sameTask && row.fallbackId !== primaryId ? row.fallbackId : "",
    extraFallbackIds: sameTask ? row.extraFallbackIds.filter((id) => id !== primaryId) : [],
  };
}

export function withFallback(row: FallbackRow, fallbackId: string): FallbackRow {
  return {
    ...row,
    fallbackId,
    extraFallbackIds: row.extraFallbackIds.filter((id) => id !== fallbackId),
  };
}
