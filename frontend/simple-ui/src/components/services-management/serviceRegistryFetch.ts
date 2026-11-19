import { listServicesPaginated } from "../../services/servicesManagementService";
import type { Service } from "../../types/platform";
import {
  SERVICE_LIST_COLUMNS,
  SERVICE_SORTABLE_COLUMN_IDS,
  serviceListFilterParams,
} from "./serviceListColumns";
import { statusFilterToApiValue } from "./serviceRegistryFilters";

export type RegistryFetchOptions = {
  silent?: boolean;
  commit?: boolean;
  taskType?: string;
  status?: string;
};

export type RegistryFetchContext = {
  enabledTaskTypesParam?: string;
  serverFilters: Record<string, string>;
  taskFilterColumnId?: string;
  statusFilterColumnId?: string;
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

export async function fetchRegistryServicesPage(
  context: RegistryFetchContext,
  options: RegistryFetchOptions = {},
): Promise<{ items: Service[]; total: number }> {
  // Server-side sort over the full dataset (incl. prices). Omit sort_by when
  // the user has not chosen a column — BE default is published first, then newest.
  let sortBy: string | undefined;
  let sortOrder: "asc" | "desc" | undefined;
  if (context.sortMode === "sorted" && SERVICE_SORTABLE_COLUMN_IDS.has(context.sortKey)) {
    sortBy = context.sortKey;
    sortOrder = context.sortDirection;
  }
  const params = {
    offset: (context.registryPage - 1) * context.registryPageSize,
    limit: context.registryPageSize,
    query: serviceListFilterParams({
      // Built-in columns: filters do not depend on the configured columns.
      columns: SERVICE_LIST_COLUMNS,
      filters: mergeServerFilters(context, options),
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

export function applyServicePublishPatch(
  service: Service,
  serviceId: string,
  isPublished: boolean,
  freshService?: Service,
): Service {
  if (service.serviceId !== serviceId) return service;
  if (freshService) return freshService;
  if (isPublished) {
    // servicePublishedOnMillis prefers publishedAt, so set both or a
    // re-publish keeps showing the previous publish date.
    const now = Date.now();
    return {
      ...service,
      isPublished,
      publishedOn: Math.floor(now / 1000),
      publishedAt: new Date(now).toISOString(),
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
