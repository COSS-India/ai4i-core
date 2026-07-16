import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { METERING, type MeteringSubTab } from "../config/meteringConstants";
import { listTenants } from "../services/tenantService";
import type {
  MeteringResponseMeta,
  MeteringTopN,
  MeteringWindow,
} from "../types/metering";
import {
  fetchMeteringOverview,
  fetchMeteringServiceConsumption,
  fetchMeteringTenantConsumption,
  parseMeteringError,
  type MeteringContext,
} from "../services/meteringService";
import { getMeteringRoleViewConfig } from "../utils/rbac";
import { meteringQueryDefaults, meteringQueryKey } from "../utils/meteringQuery";
import { resolveMeteringGeneratedAt, formatMeteringDataStateBanner } from "../utils/meteringFormatters";
import { getTenantIdFromToken } from "../utils/helpers";

export interface TenantPreviewOption {
  id: string;
  organisation: string;
  plan?: "Enterprise" | "Pro";
}

interface UseMeteringDashboardOptions {
  userRoles?: string[];
  tenantId?: string | null;
}

export function useMeteringDashboard({ userRoles, tenantId }: UseMeteringDashboardOptions) {
  const roleViewConfig = useMemo(
    () => getMeteringRoleViewConfig(userRoles),
    [userRoles],
  );

  const isAdopterView = roleViewConfig.defaultView === "adopter";
  const isTenantView = roleViewConfig.defaultView === "tenant";

  const [subTab, setSubTab] = useState<MeteringSubTab>(() =>
    getMeteringRoleViewConfig(userRoles).defaultView === "tenant"
      ? METERING.DEFAULTS.TENANT_SUB_TAB
      : METERING.DEFAULTS.SUB_TAB,
  );
  const [timeWindow, setTimeWindow] = useState<MeteringWindow>(METERING.DEFAULTS.TIME_WINDOW);
  const [topN, setTopN] = useState<MeteringTopN>(METERING.DEFAULTS.TOP_N);
  const [scopeTenantId, setScopeTenantId] = useState("");
  const [tenantHeatmapServices, setTenantHeatmapServices] = useState<string[] | null>(null);
  const [refreshNonce, setRefreshNonce] = useState(0);

  useEffect(() => {
    setTenantHeatmapServices(null);
  }, [subTab, timeWindow, topN]);

  const tenantsQuery = useQuery({
    queryKey: meteringQueryKey(METERING.QUERY.SCOPES.TENANT_DIRECTORY),
    queryFn: () => listTenants(),
    enabled: isAdopterView,
    staleTime: METERING.QUERY.TENANT_DIRECTORY_STALE_MS,
  });

  const previewTenants: TenantPreviewOption[] = useMemo(
    () =>
      (tenantsQuery.data?.tenants ?? []).map((t) => ({
        id: t.tenant_id,
        organisation: t.organisation,
      })),
    [tenantsQuery.data?.tenants],
  );

  const tenantOrganisationById = useMemo(() => {
    const map: Record<string, string> = {};
    (tenantsQuery.data?.tenants ?? []).forEach((t) => {
      if (t.tenant_id && t.organisation) {
        map[String(t.tenant_id)] = t.organisation;
      }
    });
    return map;
  }, [tenantsQuery.data?.tenants]);

  const effectiveTenantId = isTenantView
    ? tenantId?.trim() || getTenantIdFromToken() || null
    : scopeTenantId || null;

  const tenantOverviewEnabled = isTenantView && !!effectiveTenantId;

  const ctx: MeteringContext = useMemo(
    () => ({
      isPlatformAdmin: isAdopterView,
      tenantId: effectiveTenantId,
      previewTenantId: null,
      organisation: null,
    }),
    [isAdopterView, effectiveTenantId],
  );

  const queryTenantId = scopeTenantId || (isTenantView ? effectiveTenantId : null);

  const overviewQuery = useQuery({
    queryKey: meteringQueryKey(
      METERING.QUERY.SCOPES.OVERVIEW,
      timeWindow,
      queryTenantId,
      roleViewConfig.defaultView,
      isAdopterView,
    ),
    queryFn: () => fetchMeteringOverview(timeWindow, ctx, queryTenantId),
    enabled: isAdopterView || tenantOverviewEnabled,
    ...meteringQueryDefaults,
  });

  const overview = overviewQuery.data;

  const tenantQuery = useQuery({
    queryKey: meteringQueryKey(
      METERING.QUERY.SCOPES.TENANT,
      timeWindow,
      topN,
      tenantHeatmapServices?.join(",") ?? METERING.QUERY.HEATMAP_SERVICES_ALL,
      queryTenantId,
    ),
    queryFn: () =>
      fetchMeteringTenantConsumption(timeWindow, topN, tenantHeatmapServices, queryTenantId),
    enabled: isAdopterView && subTab === METERING.SUB_TAB.TENANT,
    ...meteringQueryDefaults,
  });

  const serviceQueryEnabled =
    subTab === METERING.SUB_TAB.SERVICE &&
    (isAdopterView || tenantOverviewEnabled);

  const serviceQuery = useQuery({
    queryKey: meteringQueryKey(
      METERING.QUERY.SCOPES.SERVICE,
      timeWindow,
      queryTenantId,
      roleViewConfig.defaultView,
      isAdopterView,
    ),
    queryFn: () => fetchMeteringServiceConsumption(timeWindow, ctx, queryTenantId),
    enabled: serviceQueryEnabled,
    ...meteringQueryDefaults,
  });

  const primaryMeteringResponse = useMemo((): MeteringResponseMeta | null => {
    if (isAdopterView && subTab === METERING.SUB_TAB.TENANT && tenantQuery.data) {
      return tenantQuery.data;
    }
    if (subTab === METERING.SUB_TAB.SERVICE && serviceQuery.data) {
      return serviceQuery.data;
    }
    return overview ?? null;
  }, [isAdopterView, subTab, tenantQuery.data, serviceQuery.data, overview]);

  const dataStateBanner = useMemo(() => {
    if (subTab === METERING.SUB_TAB.USAGE_SPEND) return null;
    return formatMeteringDataStateBanner(
      primaryMeteringResponse?.data_state,
      primaryMeteringResponse?.generated_at,
    );
  }, [subTab, primaryMeteringResponse?.data_state, primaryMeteringResponse?.generated_at]);

  const primaryError = useMemo(() => {
    if (subTab === METERING.SUB_TAB.USAGE_SPEND) return null;
    const err = overviewQuery.error || serviceQuery.error || tenantQuery.error;
    return err ? parseMeteringError(err) : null;
  }, [subTab, overviewQuery.error, serviceQuery.error, tenantQuery.error]);

  const isLoading =
    (isAdopterView && overviewQuery.isLoading) ||
    (isTenantView &&
      subTab !== METERING.SUB_TAB.USAGE_SPEND &&
      overviewQuery.isLoading &&
      tenantOverviewEnabled);

  // Request Volume chart is an Overview-only section now.
  const requestVolumeGraph = overview?.request_volume ?? null;

  const isRefreshing =
    overviewQuery.isFetching ||
    (isAdopterView && subTab === METERING.SUB_TAB.TENANT && tenantQuery.isFetching) ||
    (serviceQueryEnabled && serviceQuery.isFetching);

  const handleRefresh = () => {
    setRefreshNonce((n) => n + 1);
    overviewQuery.refetch();
    if (isAdopterView && subTab === METERING.SUB_TAB.TENANT) {
      tenantQuery.refetch();
    }
    if (serviceQueryEnabled) {
      serviceQuery.refetch();
    }
  };

  const organisationLabel = overview?.scope.organisation ?? null;

  const lastGeneratedAt = useMemo(
    () =>
      resolveMeteringGeneratedAt([
        (isAdopterView || tenantOverviewEnabled) ? overview?.generated_at : null,
        isAdopterView && subTab === METERING.SUB_TAB.TENANT
          ? tenantQuery.data?.generated_at
          : null,
        serviceQueryEnabled ? serviceQuery.data?.generated_at : null,
      ]),
    [
      isAdopterView,
      tenantOverviewEnabled,
      overview?.generated_at,
      subTab,
      tenantQuery.data?.generated_at,
      serviceQueryEnabled,
      serviceQuery.data?.generated_at,
    ],
  );

  const parseQueryError = (error: unknown) =>
    error ? parseMeteringError(error) : null;

  return {
    roleViewConfig,
    subTab,
    setSubTab,
    timeWindow,
    setTimeWindow,
    topN,
    setTopN,
    scopeTenantId,
    setScopeTenantId,
    setTenantHeatmapServices,
    isAdopterView,
    isTenantView,
    previewTenants,
    tenantOrganisationById,
    overview,
    tenantQuery,
    serviceQuery,
    isLoading,
    isRefreshing,
    handleRefresh,
    primaryError,
    dataStateBanner,
    requestVolumeGraph,
    organisationLabel,
    lastGeneratedAt,
    parseQueryError,
    refreshNonce,
    effectiveTenantId,
  };
}
