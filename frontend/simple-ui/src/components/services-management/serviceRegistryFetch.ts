import {
  fetchAllServicesMatchingFilters,
  listServicesPaginated,
} from "../../services/servicesManagementService";
import type { Service } from "../../types/platform";
import {
  serviceListFilterParams,
  type ServiceListColumnDef,
} from "./serviceListColumns";
import {
  statusFilterToApiValue,
  statusFilterToPublished,
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
  registryPage: number;
  registryPageSize: number;
  sortMode: "time" | "sorted";
  sortKey: string;
  sortDirection: "asc" | "desc";
};

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
  const result = await listServicesPaginated({
    offset: (context.registryPage - 1) * context.registryPageSize,
    limit: context.registryPageSize,
    query: serviceListFilterParams({
      columns: context.serviceListCatalogue,
      filters: mergeServerFilters(context, options),
      enabledTaskTypes: context.enabledTaskTypesParam,
      sortBy,
      sortOrder,
    }),
  });
  return { items: result.items, total: result.total };
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
