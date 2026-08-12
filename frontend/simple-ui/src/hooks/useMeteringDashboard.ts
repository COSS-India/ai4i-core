import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/router";
import { useEffect, useMemo, useState } from "react";
import { METERING, type MeteringSubTab } from "../config/meteringConstants";
import { useInferenceTypes } from "./useInferenceTypes";
import { toMeteringKey } from "../utils/meteringTaskKey";
import { listTenants } from "../services/tenantService";
import type {
  MeteringResponseMeta,
  MeteringTopN,
  MeteringWindow,
} from "../types/metering";
import {
  fetchMeteringModelConsumption,
  fetchMeteringOverview,
  fetchMeteringTenantConsumption,
  parseMeteringError,
  type MeteringContext,
} from "../services/meteringService";
import { getMeteringRoleViewConfig } from "../utils/rbac";
import { meteringQueryDefaults, meteringQueryKey } from "../utils/meteringQuery";
import { resolveMeteringGeneratedAt, formatMeteringDataStateBanner } from "../utils/meteringFormatters";
import { getTenantIdFromToken } from "../utils/helpers";

function isMeteringSubTab(
  value: string,
  tabs: ReadonlyArray<{ id: string }>,
): value is MeteringSubTab {
  return tabs.some((t) => t.id === value);
}

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
  const router = useRouter();
  const roleViewConfig = useMemo(
    () => getMeteringRoleViewConfig(userRoles),
    [userRoles],
  );

  const isAdopterView = roleViewConfig.defaultView === "adopter";
  const isTenantView = roleViewConfig.defaultView === "tenant";

  // Frontend-owned enabled set (ENABLED_TASK_TYPES runtime config). Passed as
  // `task_types=` on metering APIs so the backend scopes metrics; UI renders
  // the response as-is. null while the catalog is still loading.
  //
  // Metering keys use SERVICE_BREAKDOWN_CONFIG form (underscore, e.g.
  // "language_detection"), not the yaml name (hyphen) — map before sending.
  const { taskTypeNames } = useInferenceTypes();
  const enabledServices = useMemo(
    () => (taskTypeNames.length > 0 ? taskTypeNames.map(toMeteringKey) : null),
    [taskTypeNames],
  );

  const availableSubTabs = isTenantView ? METERING.TENANT_SUB_TABS : METERING.SUB_TABS;

  const [subTab, setSubTab] = useState<MeteringSubTab>(() =>
    getMeteringRoleViewConfig(userRoles).defaultView === "tenant"
      ? METERING.DEFAULTS.TENANT_SUB_TAB
      : METERING.DEFAULTS.SUB_TAB,
  );
  const [timeWindow, setTimeWindow] = useState<MeteringWindow>(METERING.DEFAULTS.TIME_WINDOW);
  const [topN, setTopN] = useState<MeteringTopN>(METERING.DEFAULTS.TOP_N);
  const [scopeTenantId, setScopeTenantId] = useState("");
  // UNDO: restore heatmap service-filter state when re-enabling "Select services".
  // const [tenantHeatmapServices, setTenantHeatmapServices] = useState<string[] | null>(null);
  const [refreshNonce, setRefreshNonce] = useState(0);

  // Honor ?tab= so login/Home can deep-link to Overview (and refresh keeps the tab).
  useEffect(() => {
    if (!router.isReady) return;
    const raw = router.query.tab;
    if (typeof raw !== "string" || !isMeteringSubTab(raw, availableSubTabs)) return;
    setSubTab(raw);
  }, [router.isReady, router.query.tab, availableSubTabs]);

  // UNDO: reset heatmap service filter when controls change.
  // useEffect(() => {
  //   setTenantHeatmapServices(null);
  // }, [subTab, timeWindow, topN]);

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
      enabledServices?.join(",") ?? METERING.QUERY.HEATMAP_SERVICES_ALL,
    ),
    queryFn: () =>
      fetchMeteringOverview(timeWindow, ctx, queryTenantId, enabledServices),
    enabled: isAdopterView || tenantOverviewEnabled,
    ...meteringQueryDefaults,
  });

  const overview = overviewQuery.data;

  const tenantQuery = useQuery({
    queryKey: meteringQueryKey(
      METERING.QUERY.SCOPES.TENANT,
      timeWindow,
      topN,
      // UNDO: tenantHeatmapServices?.join(",") ?? METERING.QUERY.HEATMAP_SERVICES_ALL,
      enabledServices?.join(",") ?? METERING.QUERY.HEATMAP_SERVICES_ALL,
      queryTenantId,
    ),
    queryFn: () =>
      fetchMeteringTenantConsumption(
        timeWindow,
        topN,
        enabledServices,
        queryTenantId,
      ),
    enabled: isAdopterView && subTab === METERING.SUB_TAB.TENANT,
    placeholderData: keepPreviousData,
    ...meteringQueryDefaults,
  });

  const modelQueryEnabled =
    subTab === METERING.SUB_TAB.MODEL &&
    (isAdopterView || tenantOverviewEnabled);

  const modelQuery = useQuery({
    queryKey: meteringQueryKey(
      METERING.QUERY.SCOPES.MODEL,
      timeWindow,
      queryTenantId,
      roleViewConfig.defaultView,
      isAdopterView,
    ),
    queryFn: () => fetchMeteringModelConsumption(timeWindow, ctx, queryTenantId),
    enabled: modelQueryEnabled,
    ...meteringQueryDefaults,
  });

  const primaryMeteringResponse = useMemo((): MeteringResponseMeta | null => {
    if (isAdopterView && subTab === METERING.SUB_TAB.TENANT && tenantQuery.data) {
      return tenantQuery.data;
    }
    if (subTab === METERING.SUB_TAB.MODEL && modelQuery.data) {
      return modelQuery.data;
    }
    return overview ?? null;
  }, [isAdopterView, subTab, tenantQuery.data, modelQuery.data, overview]);

  const dataStateBanner = useMemo(() => {
    if (subTab === METERING.SUB_TAB.USAGE_SPEND) return null;
    return formatMeteringDataStateBanner(
      primaryMeteringResponse?.data_state,
      primaryMeteringResponse?.generated_at,
    );
  }, [subTab, primaryMeteringResponse?.data_state, primaryMeteringResponse?.generated_at]);

  const primaryError = useMemo(() => {
    if (subTab === METERING.SUB_TAB.USAGE_SPEND) return null;
    const err =
      overviewQuery.error || modelQuery.error || tenantQuery.error;
    return err ? parseMeteringError(err) : null;
  }, [subTab, overviewQuery.error, modelQuery.error, tenantQuery.error]);

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
    (modelQueryEnabled && modelQuery.isFetching);

  const handleRefresh = () => {
    setRefreshNonce((n) => n + 1);
    overviewQuery.refetch();
    if (isAdopterView && subTab === METERING.SUB_TAB.TENANT) {
      tenantQuery.refetch();
    }
    if (modelQueryEnabled) {
      modelQuery.refetch();
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
        modelQueryEnabled ? modelQuery.data?.generated_at : null,
      ]),
    [
      isAdopterView,
      tenantOverviewEnabled,
      overview?.generated_at,
      subTab,
      tenantQuery.data?.generated_at,
      modelQueryEnabled,
      modelQuery.data?.generated_at,
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
    // UNDO: setTenantHeatmapServices,
    isAdopterView,
    isTenantView,
    previewTenants,
    tenantOrganisationById,
    overview,
    tenantQuery,
    modelQuery,
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
