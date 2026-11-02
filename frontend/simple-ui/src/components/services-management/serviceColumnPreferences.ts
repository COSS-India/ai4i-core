import type { ServiceListColumnDef } from "./serviceListColumns";
import {
  defaultServiceListColumnIds,
  loadServiceListColumns,
  resolveServiceListColumns,
  saveServiceListColumns,
} from "./serviceListColumns";
import {
  getServiceColumnPreference,
  resetServiceColumnPreference,
  saveServiceColumnPreference,
} from "../../services/servicesManagementService";
import { showError } from "../../utils/errorHandler";

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

export async function loadVisibleServiceColumns(options: {
  userId: string;
  usesServer: boolean;
  catalogue: readonly ServiceListColumnDef[];
}): Promise<string[]> {
  const { userId, usesServer, catalogue } = options;
  if (!usesServer) {
    return loadServiceListColumns(userId, undefined, catalogue);
  }
  try {
    const preference = await getServiceColumnPreference();
    // Prefer the API list (role defaults when isDefault, else saved selection).
    return resolveServiceListColumns(preference?.visibleColumns, catalogue);
  } catch (error) {
    console.warn("Column preference could not be loaded.", error);
    return loadServiceListColumns(userId, undefined, catalogue);
  }
}

export function persistVisibleServiceColumns(options: {
  userId: string;
  usesServer: boolean;
  catalogue: readonly ServiceListColumnDef[];
  columnIds: readonly string[];
}): string[] {
  const { userId, usesServer, catalogue, columnIds } = options;
  if (!usesServer) {
    return saveServiceListColumns(userId, columnIds, undefined, catalogue);
  }
  const resolved = resolveServiceListColumns(columnIds, catalogue);
  saveServiceColumnPreference(resolved).catch((error) => showError(error));
  return resolved;
}

export async function resetVisibleServiceColumns(options: {
  userId: string;
  usesServer: boolean;
  catalogue: readonly ServiceListColumnDef[];
}): Promise<string[]> {
  const { userId, usesServer, catalogue } = options;
  const defaults = defaultServiceListColumnIds(catalogue);
  if (!usesServer) {
    saveServiceListColumns(userId, defaults, undefined, catalogue);
    return defaults;
  }
  try {
    const preference = await resetServiceColumnPreference();
    return resolveServiceListColumns(preference?.visibleColumns ?? null, catalogue);
  } catch (error) {
    showError(error);
    return defaults;
  }
}
