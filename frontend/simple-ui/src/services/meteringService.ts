import { apiService } from "./api";
import { apiEndpoints } from "./apiEndpoints";
import {
  overviewResponseSchema,
  serviceConsumptionResponseSchema,
  tenantConsumptionResponseSchema,
} from "./dto/schemas/metering";
import {
  getMockOverview,
  getMockServiceConsumption,
  getMockTenantConsumption,
} from "../data/meteringMockData";
import type {
  MeteringTopN,
  MeteringWindow,
  OverviewResponse,
  ServiceConsumptionResponse,
  TenantConsumptionResponse,
} from "../types/metering";

const USE_MOCK = process.env.NEXT_PUBLIC_METERING_USE_MOCK === "true";

export interface MeteringContext {
  isPlatformAdmin: boolean;
  organisation?: string | null;
  tenantId?: string | null;
  /** Admin tenant-preview: pass selected tenant as tenant_id query param. */
  previewTenantId?: string | null;
}

export interface MeteringFetchResult<T> {
  data: T;
  isMock: boolean;
}

export function parseMeteringError(error: unknown): string {
  const status = (error as { status?: number })?.status;
  const message = error instanceof Error ? error.message : "Failed to load metering data.";

  if (status === 503) {
    return "Metering data is temporarily unavailable. Prometheus may not be configured.";
  }
  if (status === 403) {
    return message || "You do not have permission to view this metering data.";
  }
  if (status === 400) {
    return message || "Invalid metering request parameters.";
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
  window: MeteringWindow,
  ctx: MeteringContext,
  tenantId?: string | null,
  extra?: Record<string, string>,
): URLSearchParams {
  const params = new URLSearchParams({ window, ...extra });
  const scopedTenantId = resolveScopedTenantId(ctx, tenantId);
  if (scopedTenantId) {
    params.set("tenant_id", scopedTenantId);
  }
  return params;
}

async function fetchWithMockFallback<T>(
  fetcher: () => Promise<T>,
  mockFactory: () => T,
): Promise<MeteringFetchResult<T>> {
  if (USE_MOCK) {
    return { data: mockFactory(), isMock: true };
  }
  const data = await fetcher();
  return { data, isMock: false };
}

/** GET /api/v1/metering/overview */
export async function fetchMeteringOverview(
  window: MeteringWindow,
  ctx: MeteringContext,
  tenantId?: string | null,
): Promise<MeteringFetchResult<OverviewResponse>> {
  const params = buildMeteringParams(window, ctx, tenantId);

  return fetchWithMockFallback(
    async () => {
      const { data } = await apiService.get<OverviewResponse>(
        `${apiEndpoints.metering.overview}?${params.toString()}`,
        { responseSchema: overviewResponseSchema },
      );
      return data;
    },
    () => getMockOverview(window, ctx.isPlatformAdmin, ctx.organisation),
  );
}

/** GET /api/v1/metering/tenant-consumption — platform admin only. */
export async function fetchMeteringTenantConsumption(
  window: MeteringWindow,
  limit: MeteringTopN,
  services?: string[] | null,
): Promise<MeteringFetchResult<TenantConsumptionResponse>> {
  const extra: Record<string, string> = { limit: String(limit) };
  if (services?.length) {
    extra.services = services.join(",");
  }
  const params = new URLSearchParams({ window, ...extra });

  return fetchWithMockFallback(
    async () => {
      const { data } = await apiService.get<TenantConsumptionResponse>(
        `${apiEndpoints.metering.tenantConsumption}?${params.toString()}`,
        { responseSchema: tenantConsumptionResponseSchema },
      );
      return data;
    },
    () => getMockTenantConsumption(window),
  );
}

/** GET /api/v1/metering/service-consumption */
export async function fetchMeteringServiceConsumption(
  window: MeteringWindow,
  ctx: MeteringContext,
  tenantId?: string | null,
): Promise<MeteringFetchResult<ServiceConsumptionResponse>> {
  const params = buildMeteringParams(window, ctx, tenantId);

  return fetchWithMockFallback(
    async () => {
      const { data } = await apiService.get<ServiceConsumptionResponse>(
        `${apiEndpoints.metering.serviceConsumption}?${params.toString()}`,
        { responseSchema: serviceConsumptionResponseSchema },
      );
      return data;
    },
    () => getMockServiceConsumption(window, ctx.isPlatformAdmin, ctx.organisation),
  );
}
