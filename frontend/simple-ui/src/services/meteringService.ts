import { METERING } from "../config/meteringConstants";
import { replaceTenantCopy } from "../utils/replaceTenantCopy";
import { apiService } from "./api";
import { apiEndpoints } from "./apiEndpoints";
import {
  modelConsumptionResponseSchema,
  overviewResponseSchema,
} from "./dto/schemas/metering";
import type {
  MeteringWindow,
  ModelConsumptionResponse,
  OverviewResponse,
} from "../types/metering";

export interface MeteringContext {
  isPlatformAdmin: boolean;
  organisation?: string | null;
  tenantId?: string | null;
  /** Admin tenant-preview: pass selected tenant as tenant_id query param. */
  previewTenantId?: string | null;
}

function withQuery(path: string, search: URLSearchParams): string {
  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

export function parseMeteringError(error: unknown): string {
  const status = (error as { status?: number })?.status;
  const message =
    error instanceof Error ? error.message : METERING.ERRORS.LOAD_FAILED;

  if (status === 503) {
    return replaceTenantCopy(METERING.ERRORS.UNAVAILABLE_503);
  }
  if (status === 403) {
    return replaceTenantCopy(message || METERING.ERRORS.FORBIDDEN_403);
  }
  if (status === 400) {
    return replaceTenantCopy(message || METERING.ERRORS.BAD_REQUEST_400);
  }
  return replaceTenantCopy(message);
}

function resolveScopedTenantId(
  ctx: MeteringContext,
  tenantId?: string | null,
): string | null {
  return tenantId?.trim() || ctx.previewTenantId?.trim() || ctx.tenantId?.trim() || null;
}

function buildMeteringParams(
  timeWindow: MeteringWindow,
  ctx: MeteringContext,
  tenantId?: string | null,
  extra?: Record<string, string>,
): URLSearchParams {
  const params = new URLSearchParams({ window: timeWindow, ...extra });
  const scopedTenantId = resolveScopedTenantId(ctx, tenantId);
  if (scopedTenantId) {
    params.set("tenant_id", scopedTenantId);
  }
  return params;
}

function appendTaskTypesParam(
  params: URLSearchParams,
  taskTypes?: string[] | null,
): void {
  if (taskTypes?.length) params.set("task_types", taskTypes.join(","));
}

/** GET /api/v1/metering/overview */
export async function fetchMeteringOverview(
  timeWindow: MeteringWindow,
  ctx: MeteringContext,
  tenantId?: string | null,
  taskTypes?: string[] | null,
  limit: number = METERING.USAGE_CONCENTRATION_FETCH_LIMIT,
): Promise<OverviewResponse> {
  const params = buildMeteringParams(timeWindow, ctx, tenantId, {
    limit: String(limit),
  });
  appendTaskTypesParam(params, taskTypes);
  const { data } = await apiService.get<OverviewResponse>(
    withQuery(apiEndpoints.metering.overview, params),
    { responseSchema: overviewResponseSchema },
  );
  return data;
}

/** GET /api/v1/metering/model-consumption — scoped via frontend enabled task types. */
export async function fetchMeteringModelConsumption(
  timeWindow: MeteringWindow,
  ctx: MeteringContext,
  tenantId?: string | null,
  taskTypes?: string[] | null,
): Promise<ModelConsumptionResponse> {
  const params = buildMeteringParams(timeWindow, ctx, tenantId);
  appendTaskTypesParam(params, taskTypes);
  const { data } = await apiService.get<ModelConsumptionResponse>(
    withQuery(apiEndpoints.metering.modelConsumption, params),
    { responseSchema: modelConsumptionResponseSchema },
  );
  return data;
}
