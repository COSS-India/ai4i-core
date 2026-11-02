import {
  fetchAllServicesMatchingFilters,
  listServicesPaginated,
} from "../../services/servicesManagementService";
import type { Service } from "../../types/platform";
import {
  serviceListCellKey,
  serviceListFilterParams,
  type ServiceListColumnDef,
} from "./serviceListColumns";
import {
  statusFilterToApiValue,
  statusFilterToPublished,
  tierIdsForColumnSearch,
} from "./serviceRegistryFilters";

export type RegistryFetchOptions = {
  silent?: boolean;
  commit?: boolean;
  taskType?: string;
  status?: string;
};

export type RegistryFetchContext = {
  filterStatus: string;
  filterTaskType: string;
  enabledTaskTypesParam?: string;
  taskTypeNames: string[];
  serviceListUsesServer: boolean;
  serverFilters: Record<string, string>;
  taskFilterColumnId?: string;
  statusFilterColumnId?: string;
  serviceListCatalogue: readonly ServiceListColumnDef[];
  tierOptions: readonly { id: string; name: string }[];
  registryPage: number;
  registryPageSize: number;
  sortMode: "time" | "sorted";
  sortKey: string;
  sortDirection: "asc" | "desc";
  /** Comma-separated visible column ids (API catalogue only) → `columns=`. */
  columns?: string;
};

/** 422 codes GET /services returns when it rejects the `columns` selection. */
const REJECTED_COLUMNS_CODES = new Set(["INVALID_COLUMNS", "COLUMN_NOT_PERMITTED"]);

function isColumnsRejected(error: unknown): boolean {
  const response = (error as {
    response?: { status?: number; data?: { detail?: { code?: unknown } } };
  } | null)?.response;
  if (response?.status !== 422) return false;
  const code = response.data?.detail?.code;
  return typeof code === "string" && REJECTED_COLUMNS_CODES.has(code);
}

function mergeServerFilters(
  context: RegistryFetchContext,
  options: RegistryFetchOptions,
): Record<string, string> {
  const filters = { ...context.serverFilters };
  if (options.taskType !== undefined && context.taskFilterColumnId) {
    filters[context.taskFilterColumnId] = options.taskType;
  }
  if (options.status !== undefined && context.statusFilterColumnId) {
    filters[context.statusFilterColumnId] = statusFilterToApiValue(options.status);
  }
  return filters;
}

/** Tier column search stores a name. GET /services filters that column by id. */
function filtersWithTierIds(
  filters: Record<string, string>,
  columns: readonly ServiceListColumnDef[],
  tiers: readonly { id: string; name: string }[],
): Record<string, string> {
  const next = { ...filters };
  for (const column of columns) {
    if (serviceListCellKey(column.id) !== "tier") continue;
    const typed = (next[column.id] ?? "").trim();
    if (!typed) continue;
    next[column.id] = tierIdsForColumnSearch(typed, tiers);
  }
  return next;
}

export async function fetchRegistryServicesPage(
  context: RegistryFetchContext,
  options: RegistryFetchOptions = {},
): Promise<{ items: Service[]; total: number }> {
  let statusFilter = context.filterStatus;
  if (options.status !== undefined) statusFilter = options.status;
  let taskTypeFilter = context.filterTaskType;
  if (options.taskType !== undefined) taskTypeFilter = options.taskType;

  if (!context.serviceListUsesServer) {
    const result = await fetchAllServicesMatchingFilters({
      taskType: taskTypeFilter || undefined,
      taskTypes: context.enabledTaskTypesParam,
      isPublished: statusFilterToPublished(statusFilter),
    });
    return { items: result.items, total: result.total };
  }

  // Server-side sort over the full dataset (incl. prices). Omit sort_by when
  // the user has not chosen a column — BE default is published first, then newest.
  let sortBy: string | undefined;
  let sortOrder: "asc" | "desc" | undefined;
  if (context.sortMode === "sorted" && context.sortKey) {
    const column = context.serviceListCatalogue.find(
      (entry) => entry.id === context.sortKey,
    );
    if (column?.sortable) {
      sortBy = column.id;
      sortOrder = context.sortDirection;
    }
  }
  const params = {
    offset: (context.registryPage - 1) * context.registryPageSize,
    limit: context.registryPageSize,
    query: serviceListFilterParams({
      columns: context.serviceListCatalogue,
      filters: filtersWithTierIds(
        mergeServerFilters(context, options),
        context.serviceListCatalogue,
        context.tierOptions,
      ),
      enabledTaskTypes: context.enabledTaskTypesParam,
      sortBy,
      sortOrder,
    }),
  };
  try {
    const result = await listServicesPaginated({ ...params, columns: context.columns });
    return { items: result.items, total: result.total };
  } catch (error) {
    // A stale catalogue (e.g. role changed) can name a column the API now
    // rejects. Full rows still render every column, so retry without it.
    if (!context.columns || !isColumnsRejected(error)) throw error;
    const result = await listServicesPaginated(params);
    return { items: result.items, total: result.total };
  }
}

export function shouldReplaceFullServiceIds(
  statusFilter: string,
  taskTypeFilter: string,
  taskTypeNames: string[],
): boolean {
  const statusNarrows =
    statusFilter === "published" || statusFilter === "unpublished";
  const onlyEnabledTask =
    taskTypeNames.length === 1 && taskTypeFilter === taskTypeNames[0];
  const taskNarrows = Boolean(taskTypeFilter) && !onlyEnabledTask;
  return !statusNarrows && !taskNarrows;
}

export function serviceIdsFromItems(items: Service[]): string[] {
  return items
    .map((service) => service.serviceId || service.service_id || "")
    .filter((id): id is string => Boolean(id));
}

export function mergeServiceIdLists(
  previous: string[] | null | undefined,
  next: string[],
): string[] {
  return Array.from(new Set([...(previous ?? []), ...next]));
}

export function applyServicePublishPatch(
  service: Service,
  serviceId: string,
  isPublished: boolean,
  freshService?: Service,
): Service {
  if (service.serviceId !== serviceId) return service;
  if (freshService) return freshService;
  if (isPublished) {
    return {
      ...service,
      isPublished,
      publishedOn: Math.floor(Date.now() / 1000),
    };
  }
  return { ...service, isPublished };
}

export function filterServicesForPublishStatus(
  services: Service[],
  options: {
    serviceId: string;
    isPublished: boolean;
    freshService?: Service;
    publishedOnly: boolean;
    unpublishedOnly: boolean;
  },
): Service[] {
  const next = services.map((service) =>
    applyServicePublishPatch(
      service,
      options.serviceId,
      options.isPublished,
      options.freshService,
    ),
  );
  if (options.publishedOnly) {
    return next.filter((service) => service.isPublished === true);
  }
  if (options.unpublishedOnly) {
    return next.filter((service) => service.isPublished !== true);
  }
  return next;
}

export function resolveOptionalFilterValue(
  override: string | undefined,
  current: string,
): string {
  return override ?? current;
}
