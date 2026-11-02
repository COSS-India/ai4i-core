import type { ModelListColumnDef } from "./modelListColumns";
import {
  defaultModelListColumnIds,
  loadModelListColumns,
  saveModelListColumns,
} from "./modelListColumns";

export function sameModelColumnIds(
  left: readonly string[],
  right: readonly string[],
): boolean {
  if (left.length !== right.length) return false;
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] !== right[index]) return false;
  }
  return true;
}

export function nextVisibleModelColumnIds(
  current: readonly string[],
  next: readonly string[],
): string[] {
  if (sameModelColumnIds(current, next)) return [...current];
  return [...next];
}

/** Browser-local until BE registers `model-list` column preferences. */
export function loadVisibleModelColumns(options: {
  userId: string;
  catalogue: readonly ModelListColumnDef[];
}): string[] {
  return loadModelListColumns(options.userId, undefined, options.catalogue);
}

export function persistVisibleModelColumns(options: {
  userId: string;
  catalogue: readonly ModelListColumnDef[];
  columnIds: readonly string[];
}): string[] {
  return saveModelListColumns(
    options.userId,
    options.columnIds,
    undefined,
    options.catalogue,
  );
}

export function resetVisibleModelColumns(options: {
  userId: string;
  catalogue: readonly ModelListColumnDef[];
}): string[] {
  const defaults = defaultModelListColumnIds(options.catalogue);
  saveModelListColumns(options.userId, defaults, undefined, options.catalogue);
  return defaults;
}
