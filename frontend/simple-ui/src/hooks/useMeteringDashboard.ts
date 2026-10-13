import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/router";
import { useEffect, useMemo, useState } from "react";
import { METERING, type MeteringSubTab } from "../config/meteringConstants";
import { useInferenceTypes } from "./useInferenceTypes";
import { toMeteringKey } from "../utils/meteringTaskKey";
import { useTenantsList } from "./useTenantsList";
import type {
  MeteringDayKey,
  MeteringPeriod,
  MeteringResponseMeta,
  MeteringTopN,
} from "../types/metering";
import {
  fetchMeteringModelConsumption,
  fetchMeteringOverview,
  parseMeteringError,
  type MeteringContext,
} from "../services/meteringService";
import { fetchUsageSummary } from "../services/usageSpendService";
import { billingPeriodValue } from "../utils/usageSpendHelpers";
import type { KeyMetricsSupplement } from "../types/metering";
import { getMeteringRoleViewConfig } from "../utils/rbac";
import {
  isInvalidPeriodError,
  meteringQueryDefaults,
  meteringQueryKey,
} from "../utils/meteringQuery";
import { showToast } from "../utils/toast";
import { resolveMeteringGeneratedAt, formatMeteringDataStateBanner } from "../utils/meteringFormatters";
import { getTenantIdFromToken } from "../utils/helpers";
import { istDayKey, periodQueryKeyParts } from "../utils/meteringDateRange";

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

  const availableSubTabs = METERING.SUB_TABS;

  const [subTab, setSubTab] = useState<MeteringSubTab>(METERING.DEFAULTS.SUB_TAB);
  const [period, setPeriod] = useState<MeteringPeriod>(METERING.DEFAULTS.PERIOD);
  const isDefaultPeriod = period.key === METERING.DEFAULTS.PERIOD.key;
  const [topN, setTopN] = useState<MeteringTopN>(METERING.DEFAULTS.TOP_N);
  const [scopeTenantId, setScopeTenantId] = useState("");
  const [refreshNonce, setRefreshNonce] = useState(0);

  // Honor ?tab= so login/Home can deep-link to Overview (and refresh keeps the tab).
  useEffect(() => {
    if (!router.isReady) return;
    const raw = router.query.tab;
    if (typeof raw !== "string" || !isMeteringSubTab(raw, availableSubTabs)) return;
    setSubTab(raw);
  }, [router.isReady, router.query.tab, availableSubTabs]);

  const tenantsQuery = useTenantsList({
    enabled: isAdopterView,
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

  // Wait for ENABLED_TASK_TYPES before metering fetches — no "all services" path.
  const enabledServicesKey = enabledServices?.join(",") ?? "";
  const enabledServicesReady = enabledServices != null;

  const overviewEnabled = enabledServicesReady && (isAdopterView || tenantOverviewEnabled);

  const overviewQueryOptions = (p: MeteringPeriod) => ({
    queryKey: meteringQueryKey(
      METERING.QUERY.SCOPES.OVERVIEW,
      ...periodQueryKeyParts(p),
      queryTenantId,
      roleViewConfig.defaultView,
      isAdopterView,
      enabledServicesKey,
      refreshNonce,
    ),
    queryFn: () =>
      fetchMeteringOverview(
        p,
        ctx,
        queryTenantId,
        enabledServices,
        METERING.USAGE_CONCENTRATION_FETCH_LIMIT,
      ),
    ...meteringQueryDefaults,
  });

  const overviewQuery = useQuery({
    ...overviewQueryOptions(period),
    enabled: overviewEnabled,
  });

  const overview = overviewQuery.data;

  // The overview loads on every tab, so it is where a rejected custom range
  // shows up first. The error toast carries the API's reason; fall back to the
  // default period so every tab is not left on an error.
  useEffect(() => {
    if (period.key !== "custom" || !isInvalidPeriodError(overviewQuery.error)) return;
    showToast({ type: "info", message: METERING.ERRORS.INVALID_PERIOD_RESET });
    setPeriod(METERING.DEFAULTS.PERIOD);
  }, [period.key, overviewQuery.error]);

  // Date picker floor: the IST day the institution was onboarded, or the first
  // recorded usage in scope when there is no single institution.
  const firstPickableDay = useMemo((): MeteringDayKey | null => {
    const ms = Date.parse(overview?.onboarded_at ?? overview?.first_usage_at ?? "");
    return Number.isNaN(ms) ? null : istDayKey(ms);
  }, [overview?.onboarded_at, overview?.first_usage_at]);

  // Key metrics (`platform_adoption`) ignore the period, but a fetch for
  // another period (or its failure) must not blank them, so they read the
  // default-period overview — the cache entry from the dashboard's first load.
  const keyMetricsOverviewQuery = useQuery({
    ...overviewQueryOptions(METERING.DEFAULTS.PERIOD),
    enabled: overviewEnabled && isAdopterView && !isDefaultPeriod,
  });

  const keyMetricsOverview = isDefaultPeriod ? overview : keyMetricsOverviewQuery.data;

  const modelQueryEnabled =
    enabledServicesReady &&
    subTab === METERING.SUB_TAB.MODEL &&
    (isAdopterView || tenantOverviewEnabled);

  const modelQuery = useQuery({
    queryKey: meteringQueryKey(
      METERING.QUERY.SCOPES.MODEL,
      ...periodQueryKeyParts(period),
      queryTenantId,
      roleViewConfig.defaultView,
      isAdopterView,
      enabledServicesKey,
      refreshNonce,
    ),
    queryFn: () =>
      fetchMeteringModelConsumption(
        period,
        ctx,
        queryTenantId,
        enabledServices,
      ),
    enabled: modelQueryEnabled,
    ...meteringQueryDefaults,
  });

  const keyMetricsBudgetQuery = useQuery({
    queryKey: ["usage-summary", "key-metrics", billingPeriodValue("current"), refreshNonce],
    queryFn: () => fetchUsageSummary({ billingPeriod: billingPeriodValue("current") }),
    enabled: isAdopterView,
    ...meteringQueryDefaults,
    retry: 1,
  });

  const keyMetricsSupplement = useMemo((): KeyMetricsSupplement | undefined => {
    if (!isAdopterView) return undefined;
    const adoption = keyMetricsOverview?.platform_adoption;
    return {
      total_models: adoption?.total_models,
      active_models_30d: adoption?.active_models_30d,
      tenants_budget_exhausted: keyMetricsBudgetQuery.data?.budgetExceededTenants,
    };
  }, [
    isAdopterView,
    keyMetricsOverview?.platform_adoption,
    keyMetricsBudgetQuery.data?.budgetExceededTenants,
  ]);

  const primaryMeteringResponse = useMemo((): MeteringResponseMeta | null => {
    if (subTab === METERING.SUB_TAB.MODEL && modelQuery.data) {
      return modelQuery.data;
    }
    return overview ?? null;
  }, [subTab, modelQuery.data, overview]);

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
      overviewQuery.error ||
      modelQuery.error ||
      (isAdopterView && !isDefaultPeriod && keyMetricsOverviewQuery.error) ||
      (isAdopterView && keyMetricsBudgetQuery.error);
    return err ? parseMeteringError(err) : null;
  }, [
    subTab,
    isAdopterView,
    overviewQuery.error,
    modelQuery.error,
    isDefaultPeriod,
    keyMetricsOverviewQuery.error,
    keyMetricsBudgetQuery.error,
  ]);

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
    (modelQueryEnabled && modelQuery.isFetching) ||
    (isAdopterView && !isDefaultPeriod && keyMetricsOverviewQuery.isFetching) ||
    (isAdopterView && keyMetricsBudgetQuery.isFetching);

  const handleRefresh = () => {
    setRefreshNonce((n) => n + 1);
    overviewQuery.refetch();
    if (modelQueryEnabled) {
      modelQuery.refetch();
    }
    if (isAdopterView) {
      if (!isDefaultPeriod) keyMetricsOverviewQuery.refetch();
      keyMetricsBudgetQuery.refetch();
    }
  };

  const organisationLabel = overview?.scope.organisation ?? null;

  const lastGeneratedAt = useMemo(
    () =>
      resolveMeteringGeneratedAt([
        (isAdopterView || tenantOverviewEnabled) ? overview?.generated_at : null,
        modelQueryEnabled ? modelQuery.data?.generated_at : null,
      ]),
    [
      isAdopterView,
      tenantOverviewEnabled,
      overview?.generated_at,
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
    period,
    setPeriod,
    firstPickableDay,
    topN,
    setTopN,
    scopeTenantId,
    setScopeTenantId,
    isAdopterView,
    isTenantView,
    previewTenants,
    tenantOrganisationById,
    overview,
    keyMetricsOverview,
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
    keyMetricsSupplement,
  };
}
