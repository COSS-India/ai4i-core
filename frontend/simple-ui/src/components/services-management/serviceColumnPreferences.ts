import type { ServiceListColumnDef } from "./serviceListColumns";
import {
  defaultServiceListColumnIds,
  loadServiceListColumns,
  saveServiceListColumns,
} from "./serviceListColumns";

export function sameServiceColumnIds(
  left: readonly string[],
  right: readonly string[],
): boolean {
  if (left.length !== right.length) return false;
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] !== right[index]) return false;
  }
  return true;
}

export function nextVisibleColumnIds(
  current: readonly string[],
  next: readonly string[],
): string[] {
  if (sameServiceColumnIds(current, next)) return [...current];
  return [...next];
}

/** Browser-local column selection, as for the Model List. */
export function loadVisibleServiceColumns(options: {
  userId: string;
  catalogue: readonly ServiceListColumnDef[];
}): string[] {
  return loadServiceListColumns(options.userId, undefined, options.catalogue);
}

export function persistVisibleServiceColumns(options: {
  userId: string;
  catalogue: readonly ServiceListColumnDef[];
  columnIds: readonly string[];
}): string[] {
  return saveServiceListColumns(
    options.userId,
    options.columnIds,
    undefined,
    options.catalogue,
  );
}

export function resetVisibleServiceColumns(options: {
  userId: string;
  catalogue: readonly ServiceListColumnDef[];
}): string[] {
  const defaults = defaultServiceListColumnIds(options.catalogue);
  saveServiceListColumns(options.userId, defaults, undefined, options.catalogue);
  return defaults;
}
