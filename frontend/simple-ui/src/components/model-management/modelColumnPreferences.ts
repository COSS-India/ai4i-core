import type { ModelListColumnDef } from "./modelListColumns";
import {
  defaultModelListColumnIds,
  loadModelListColumns,
  resolveModelListColumns,
  saveModelListColumns,
} from "./modelListColumns";
import {
  getModelColumnPreference,
  resetModelColumnPreference,
  saveModelColumnPreference,
} from "../../services/modelManagementService";
import { showError } from "../../utils/errorHandler";

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

export async function loadVisibleModelColumns(options: {
  userId: string;
  usesServer: boolean;
  catalogue: readonly ModelListColumnDef[];
}): Promise<string[]> {
  const { userId, usesServer, catalogue } = options;
  if (!usesServer) {
    return loadModelListColumns(userId, undefined, catalogue);
  }
  try {
    const preference = await getModelColumnPreference();
    return resolveModelListColumns(preference?.visibleColumns, catalogue);
  } catch (error) {
    console.warn("Model column preference could not be loaded.", error);
    return loadModelListColumns(userId, undefined, catalogue);
  }
}

export function persistVisibleModelColumns(options: {
  userId: string;
  usesServer: boolean;
  catalogue: readonly ModelListColumnDef[];
  columnIds: readonly string[];
}): string[] {
  const { userId, usesServer, catalogue, columnIds } = options;
  if (!usesServer) {
    return saveModelListColumns(userId, columnIds, undefined, catalogue);
  }
  const resolved = resolveModelListColumns(columnIds, catalogue);
  saveModelColumnPreference(resolved).catch((error) => showError(error));
  return resolved;
}

export async function resetVisibleModelColumns(options: {
  userId: string;
  usesServer: boolean;
  catalogue: readonly ModelListColumnDef[];
}): Promise<string[]> {
  const { userId, usesServer, catalogue } = options;
  const defaults = defaultModelListColumnIds(catalogue);
  if (!usesServer) {
    saveModelListColumns(userId, defaults, undefined, catalogue);
    return defaults;
  }
  try {
    const preference = await resetModelColumnPreference();
    return resolveModelListColumns(preference?.visibleColumns ?? null, catalogue);
  } catch (error) {
    showError(error);
    return defaults;
  }
}
