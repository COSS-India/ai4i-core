import { METERING } from "../config/meteringConstants";
import { apiService } from "./api";
import { apiEndpoints } from "./apiEndpoints";
import {
  overviewResponseSchema,
  serviceConsumptionResponseSchema,
  tenantConsumptionResponseSchema,
} from "./dto/schemas/metering";
import type {
  MeteringTopN,
  MeteringWindow,
  OverviewResponse,
  ServiceConsumptionResponse,
  TenantConsumptionResponse,
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
    return METERING.ERRORS.UNAVAILABLE_503;
  }
  if (status === 403) {
    return message || METERING.ERRORS.FORBIDDEN_403;
  }
  if (status === 400) {
    return message || METERING.ERRORS.BAD_REQUEST_400;
  }
  return message;
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

/** GET /api/v1/metering/overview */
export async function fetchMeteringOverview(
  timeWindow: MeteringWindow,
  ctx: MeteringContext,
  tenantId?: string | null,
): Promise<OverviewResponse> {
  const params = buildMeteringParams(timeWindow, ctx, tenantId);
  const { data } = await apiService.get<OverviewResponse>(
    withQuery(apiEndpoints.metering.overview, params),
    { responseSchema: overviewResponseSchema },
  );
  return data;
}

/** GET /api/v1/metering/tenant-consumption — platform admin only. */
export async function fetchMeteringTenantConsumption(
  timeWindow: MeteringWindow,
  limit: MeteringTopN,
  taskTypes?: string[] | null,
  tenantId?: string | null,
): Promise<TenantConsumptionResponse> {
  const extra: Record<string, string> = { limit: String(limit) };
  if (taskTypes?.length) {
    extra.taskTypes = taskTypes.join(",");
  }
  if (tenantId?.trim()) {
    extra.tenant_id = tenantId.trim();
  }
  const params = new URLSearchParams({ window: timeWindow, ...extra });
  const { data } = await apiService.get<TenantConsumptionResponse>(
    withQuery(apiEndpoints.metering.tenantConsumption, params),
    { responseSchema: tenantConsumptionResponseSchema },
  );
  return data;
}

/** GET /api/v1/metering/service-consumption */
export async function fetchMeteringServiceConsumption(
  timeWindow: MeteringWindow,
  ctx: MeteringContext,
  tenantId?: string | null,
  taskTypes?: string[] | null,
): Promise<ServiceConsumptionResponse> {
  const params = buildMeteringParams(timeWindow, ctx, tenantId);
  if (taskTypes?.length) {
    params.set("taskTypes", taskTypes.join(","));
  }
  const { data } = await apiService.get<ServiceConsumptionResponse>(
    withQuery(apiEndpoints.metering.serviceConsumption, params),
    { responseSchema: serviceConsumptionResponseSchema },
  );
  return data;
}
