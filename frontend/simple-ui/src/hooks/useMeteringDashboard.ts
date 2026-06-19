import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { METERING, type MeteringSubTab } from "../config/meteringConstants";
import { listTenants } from "../services/tenantService";
import type { MeteringTopN, MeteringWindow } from "../types/metering";
import {
  fetchMeteringOverview,
  fetchMeteringServiceConsumption,
  fetchMeteringTenantConsumption,
  parseMeteringError,
  type MeteringContext,
} from "../services/meteringService";
import {
  getMeteringRoleViewConfig,
  type MeteringRoleView,
} from "../utils/rbac";
import { meteringQueryDefaults, meteringQueryKey } from "../utils/meteringQuery";
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

  const [roleView, setRoleView] = useState<MeteringRoleView>(roleViewConfig.defaultView);
  const [subTab, setSubTab] = useState<MeteringSubTab>(METERING.DEFAULTS.SUB_TAB);
  const [timeWindow, setTimeWindow] = useState<MeteringWindow>(METERING.DEFAULTS.TIME_WINDOW);
  const [topN, setTopN] = useState<MeteringTopN>(METERING.DEFAULTS.TOP_N);
  const [scopeTenantId, setScopeTenantId] = useState("");
  const [previewTenantId, setPreviewTenantId] = useState("");
  const [tenantHeatmapServices, setTenantHeatmapServices] = useState<string[] | null>(null);
  const [serviceSectionVisible, setServiceSectionVisible] = useState(false);
  const serviceSectionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setRoleView(roleViewConfig.defaultView);
  }, [roleViewConfig.defaultView]);

  useEffect(() => {
    setTenantHeatmapServices(null);
  }, [subTab, timeWindow, topN]);

  useEffect(() => {
    setServiceSectionVisible(false);
  }, [roleView, previewTenantId, timeWindow, scopeTenantId]);

  const isAdopterView = roleView === "adopter";
  const isTenantView = roleView === "tenant";

  const tenantsQuery = useQuery({
    queryKey: meteringQueryKey(METERING.QUERY.SCOPES.TENANT_DIRECTORY),
    queryFn: () => listTenants(),
    enabled: isAdopterView || (roleViewConfig.canSwitchViews && isTenantView),
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

  useEffect(() => {
    if (isTenantView && roleViewConfig.canSwitchViews && previewTenants.length > 0 && !previewTenantId) {
      setPreviewTenantId(previewTenants[0].id);
    }
  }, [isTenantView, roleViewConfig.canSwitchViews, previewTenants, previewTenantId]);

  const previewOrganisation =
    previewTenants.find((t) => t.id === previewTenantId)?.organisation ?? null;

  const isAdminPreviewingTenant = roleViewConfig.canSwitchViews && isTenantView;
  const effectiveIsPlatformAdmin = isAdopterView || isAdminPreviewingTenant;
  const effectiveTenantId = isTenantView
    ? roleViewConfig.canSwitchViews
      ? previewTenantId || null
      : tenantId?.trim() || getTenantIdFromToken() || null
    : scopeTenantId || null;

  const tenantOverviewEnabled =
    isTenantView &&
    (roleViewConfig.canSwitchViews ? !!previewTenantId : !!effectiveTenantId);

  const ctx: MeteringContext = useMemo(
    () => ({
      isPlatformAdmin: effectiveIsPlatformAdmin,
      tenantId: effectiveTenantId,
      previewTenantId: isAdminPreviewingTenant ? previewTenantId || null : null,
      organisation: isTenantView ? previewOrganisation : null,
    }),
    [
      effectiveIsPlatformAdmin,
      effectiveTenantId,
      isAdminPreviewingTenant,
      previewTenantId,
      isTenantView,
      previewOrganisation,
    ],
  );

  const queryTenantId = scopeTenantId || (isTenantView ? effectiveTenantId : null);

  const overviewQuery = useQuery({
    queryKey: meteringQueryKey(
      METERING.QUERY.SCOPES.OVERVIEW,
      timeWindow,
      queryTenantId,
      previewTenantId,
      roleView,
      effectiveIsPlatformAdmin,
    ),
    queryFn: () => fetchMeteringOverview(timeWindow, ctx, queryTenantId),
    enabled: isAdopterView || tenantOverviewEnabled,
    ...meteringQueryDefaults,
  });

  const tenantQuery = useQuery({
    queryKey: meteringQueryKey(
      METERING.QUERY.SCOPES.TENANT,
      timeWindow,
      topN,
      tenantHeatmapServices?.join(",") ?? METERING.QUERY.HEATMAP_SERVICES_ALL,
    ),
    queryFn: () => fetchMeteringTenantConsumption(timeWindow, topN, tenantHeatmapServices),
    enabled: isAdopterView && subTab === METERING.SUB_TAB.TENANT,
    ...meteringQueryDefaults,
  });

  const serviceQueryEnabled =
    (isAdopterView && subTab === METERING.SUB_TAB.SERVICE) ||
    (tenantOverviewEnabled && serviceSectionVisible);

  const serviceQuery = useQuery({
    queryKey: meteringQueryKey(
      METERING.QUERY.SCOPES.SERVICE,
      timeWindow,
      queryTenantId,
      previewTenantId,
      roleView,
      effectiveIsPlatformAdmin,
    ),
    queryFn: () => fetchMeteringServiceConsumption(timeWindow, ctx, queryTenantId),
    enabled: serviceQueryEnabled,
    ...meteringQueryDefaults,
  });

  useEffect(() => {
    if (!tenantOverviewEnabled) return;
    const el = serviceSectionRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setServiceSectionVisible(true);
        }
      },
      { rootMargin: METERING.QUERY.SCROLL_ROOT_MARGIN },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [tenantOverviewEnabled]);

  const overview = overviewQuery.data;
  const isDegraded = Boolean(
    overview?.degraded || tenantQuery.data?.degraded || serviceQuery.data?.degraded,
  );

  const primaryError = useMemo(() => {
    const err = overviewQuery.error || serviceQuery.error || tenantQuery.error;
    return err ? parseMeteringError(err) : null;
  }, [overviewQuery.error, serviceQuery.error, tenantQuery.error]);

  const isLoading =
    (isAdopterView && overviewQuery.isLoading) ||
    (isTenantView && overviewQuery.isLoading && tenantOverviewEnabled);

  const requestVolumeGraph =
    overview?.request_volume ?? serviceQuery.data?.request_volume ?? null;

  const isRefreshing =
    overviewQuery.isFetching ||
    (isAdopterView && subTab === METERING.SUB_TAB.TENANT && tenantQuery.isFetching) ||
    (serviceQueryEnabled && serviceQuery.isFetching);

  const handleRefresh = () => {
    overviewQuery.refetch();
    if (isAdopterView && subTab === METERING.SUB_TAB.TENANT) {
      tenantQuery.refetch();
    }
    if (serviceQueryEnabled) {
      serviceQuery.refetch();
    }
  };

  const totalRequestsKpi = overview?.kpis.find(
    (k) => k.key === METERING.KPI.KEYS.TOTAL_REQUESTS,
  )?.value;
  const successRateKpi = overview?.kpis.find(
    (k) => k.key === METERING.KPI.KEYS.SUCCESS_RATE,
  )?.value;

  const organisationLabel = overview?.scope.organisation ?? previewOrganisation ?? null;

  const parseQueryError = (error: unknown) =>
    error ? parseMeteringError(error) : null;

  return {
    roleViewConfig,
    roleView,
    setRoleView,
    subTab,
    setSubTab,
    timeWindow,
    setTimeWindow,
    topN,
    setTopN,
    scopeTenantId,
    setScopeTenantId,
    previewTenantId,
    setPreviewTenantId,
    setTenantHeatmapServices,
    serviceSectionRef,
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
    isDegraded,
    requestVolumeGraph,
    totalRequestsKpi,
    successRateKpi,
    organisationLabel,
    parseQueryError,
  };
}
