import React, { useCallback, useRef, useState } from "react";
import {
  Box,
  Flex,
  FormControl,
  HStack,
  Select,
  Text,
  VStack,
  useDisclosure,
} from "@chakra-ui/react";
import { METERING } from "../../config/meteringConstants";
import { fetchTenantUsageById } from "../../services/usageSpendService";
import { INSTITUTION, formatModelTaskTypeLabel } from "../../config/constants";
import { useInferenceTypes } from "../../hooks/useInferenceTypes";
import { useUsageAndSpendData } from "../../hooks/useUsageAndSpendData";
import { showToast } from "../../utils/toast";
import {
  billingPeriodValue,
  type BillingPeriodKey,
} from "../../utils/usageSpendHelpers";
import type { TenantUsageDetail, TenantUsageItem } from "../../types/usageSpend";
import SpendOverviewPanel from "./SpendOverviewPanel";
import { TenantAvatar, TierBadge } from "./UsageSpendCells";
import UsageSpendTenantDrawer from "./UsageSpendTenantDrawer";
import UsageSpendTenantTable from "./UsageSpendTenantTable";

interface UsageAndSpendTabProps {
  readonly scopeTenantId?: string | null;
  readonly isTenantView?: boolean;
  readonly tenantId?: string | null;
  readonly organisationLabel?: string | null;
  readonly refreshNonce?: number;
}

const UsageAndSpendTab: React.FC<UsageAndSpendTabProps> = ({
  scopeTenantId = null,
  isTenantView = false,
  tenantId = null,
  organisationLabel = null,
  refreshNonce = 0,
}) => {
  const [periodKey, setPeriodKey] = useState<BillingPeriodKey>("current");
  /** Period currently shown in the drawer selector (may be pending while loading). */
  const [drawerPeriodKey, setDrawerPeriodKey] = useState<BillingPeriodKey>("current");
  /** Period that `selectedTenant` was actually fetched for — drives the spend label. */
  const [loadedPeriodKey, setLoadedPeriodKey] = useState<BillingPeriodKey>("current");
  const [filterTierId, setFilterTierId] = useState("");
  const [filterTaskType, setFilterTaskType] = useState("");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selectedTenant, setSelectedTenant] = useState<TenantUsageDetail | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const detailRequestIdRef = useRef(0);
  const { isOpen: isDetailOpen, onOpen: onDetailOpen, onClose: onDetailClose } = useDisclosure();
  const { taskTypeNames } = useInferenceTypes();
  // Same allowlist as list/summary (`ENABLED_TASK_TYPES`); omit ⇒ backend returns all.
  const enabledTaskTypesParam =
    taskTypeNames.length > 0 ? taskTypeNames.join(",") : undefined;

  const data = useUsageAndSpendData({
    scopeTenantId,
    isTenantView,
    tenantId,
    refreshNonce,
    periodKey,
    filterTierId,
    filterTaskType,
    sortOrder,
    taskTypeNames,
  });

  const tenantDetail = isTenantView || data.isScoped ? (data.tenants[0] ?? null) : null;
  const orgName =
    organisationLabel?.trim() || tenantDetail?.tenantName?.trim() || null;

  const toggleExpand = useCallback((id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleTenantClick = useCallback(
    async (row: TenantUsageItem) => {
      const requestId = ++detailRequestIdRef.current;
      onDetailOpen();
      setDrawerPeriodKey(periodKey);
      setLoadedPeriodKey(periodKey);
      setIsDetailLoading(true);
      try {
        const detail = await fetchTenantUsageById(
          row.tenantId,
          data.billingPeriod,
          enabledTaskTypesParam,
        );
        if (requestId !== detailRequestIdRef.current) return;
        setSelectedTenant(detail);
      } catch {
        if (requestId !== detailRequestIdRef.current) return;
        setSelectedTenant(row);
      } finally {
        if (requestId === detailRequestIdRef.current) setIsDetailLoading(false);
      }
    },
    [onDetailOpen, data.billingPeriod, periodKey, enabledTaskTypesParam],
  );

  /**
   * Drawer period changes only update the dashboard `periodKey` after a successful
   * refetch, so the table/summary stay in sync with what the user just viewed.
   * On failure the selector reverts to `loadedPeriodKey` so the label always matches data.
   */
  const handleDrawerPeriodChange = useCallback(
    async (nextPeriodKey: BillingPeriodKey) => {
      if (nextPeriodKey === drawerPeriodKey || !selectedTenant?.tenantId) return;

      const requestId = ++detailRequestIdRef.current;
      const tenantId = selectedTenant.tenantId;
      const previousLoaded = loadedPeriodKey;

      setDrawerPeriodKey(nextPeriodKey);
      setIsDetailLoading(true);
      try {
        const detail = await fetchTenantUsageById(
          tenantId,
          billingPeriodValue(nextPeriodKey),
          enabledTaskTypesParam,
        );
        if (requestId !== detailRequestIdRef.current) return;
        setSelectedTenant(detail);
        setLoadedPeriodKey(nextPeriodKey);
        setPeriodKey(nextPeriodKey);
      } catch {
        if (requestId !== detailRequestIdRef.current) return;
        setDrawerPeriodKey(previousLoaded);
        showToast({
          type: "error",
          message: "Could not load spend for the selected billing period. Showing the previous period.",
        });
      } finally {
        if (requestId === detailRequestIdRef.current) setIsDetailLoading(false);
      }
    },
    [drawerPeriodKey, loadedPeriodKey, selectedTenant?.tenantId, enabledTaskTypesParam],
  );

  const handleDetailClose = useCallback(() => {
    detailRequestIdRef.current += 1;
    onDetailClose();
    setSelectedTenant(null);
    setIsDetailLoading(false);
  }, [onDetailClose]);

  return (
    <VStack align="stretch" spacing={5}>
      <Flex justify="space-between" align="flex-start" gap={6} flexWrap="wrap">
        {isTenantView && tenantDetail ? (
          <HStack spacing="14px" align="center">
            <TenantAvatar name={orgName || tenantDetail.tenantName} size="md" />
            <Box>
              <Text fontSize="18px" fontWeight="bold" lineHeight="1.2">
                {orgName || tenantDetail.tenantName}
              </Text>
              <Text fontSize="13px" color="gray.500">
                {METERING.ROLE_VIEWS.tenant} view
              </Text>
            </Box>
          </HStack>
        ) : (
          <Box />
        )}
        <VStack align="flex-end" spacing={2}>
          {isTenantView && tenantDetail ? <TierBadge label={tenantDetail.tier} /> : null}
          <FormControl w="auto">
            <Text
              fontSize="12px"
              color="gray.500"
              fontWeight="semibold"
              letterSpacing="0.03em"
              textAlign="right"
              mb={1}
            >
              {METERING.USAGE_SPEND.BILLING_PERIOD}
            </Text>
            <Select
              size="sm"
              value={periodKey}
              onChange={(e) => setPeriodKey(e.target.value as BillingPeriodKey)}
              borderRadius="8px"
              minW="180px"
              bg="white"
              isDisabled={isDetailOpen}
            >
              <option value="current">{METERING.USAGE_SPEND.CURRENT_MONTH}</option>
              <option value="last">{METERING.USAGE_SPEND.LAST_MONTH}</option>
            </Select>
          </FormControl>
        </VStack>
      </Flex>

      <SpendOverviewPanel
        summary={data.summaryData}
        isLoading={data.isSummaryLoading}
        error={data.summaryError}
        currency={data.currency}
        spendChangePercent={data.spendChangePercent}
        tenantDetail={null}
        showProgramMetrics={!isTenantView && !data.isScoped}
        emptyStateMessage={
          data.hasNoTierAssigned
            ? "No tier or budget assigned. Contact your administrator."
            : undefined
        }
      />

      {!data.isScoped ? (
        <HStack spacing={3} flexWrap="wrap">
          <Select
            size="sm"
            w={{ base: "full", sm: "220px" }}
            value={filterTierId}
            onChange={(e) => setFilterTierId(e.target.value)}
            borderRadius="8px"
            bg="white"
          >
            <option value="">Filter by tier · All tiers</option>
            {data.tiers.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </Select>
          <Select
            size="sm"
            w={{ base: "full", sm: "260px" }}
            value={filterTaskType}
            onChange={(e) => setFilterTaskType(e.target.value)}
            borderRadius="8px"
            bg="white"
          >
            <option value="">Filter by model task type · All</option>
            {data.taskTypeOptions.map((t) => (
              <option key={t} value={t}>
                {formatModelTaskTypeLabel(t)}
              </option>
            ))}
          </Select>
        </HStack>
      ) : null}

      <UsageSpendTenantTable
        tenants={data.tenants}
        isLoading={data.isTenantsLoading}
        errorMessage={data.tenantsError}
        emptyMessage={
          data.isScoped
            ? `No usage data available for this ${INSTITUTION.toLowerCase()}.`
            : `No ${INSTITUTION.toLowerCase()} usage data available.`
        }
        filterTaskType={filterTaskType}
        showTokenUsage={data.isScoped || Boolean(filterTaskType)}
        sortOrder={sortOrder}
        expanded={expanded}
        onToggleSort={() => setSortOrder((o) => (o === "desc" ? "asc" : "desc"))}
        onToggleExpand={toggleExpand}
        onTenantClick={handleTenantClick}
      />

      <Text fontSize="12px" color="gray.500" lineHeight="1.6">
        Spend is a sortable column. Budget shows utilization against the allocated limit. Units
        follow each service&apos;s metering definition. Tier and task type filters apply to the
        table; when a tenant changed tiers mid-period, expand it to see spend split by tier.
        Open a tenant for the full task-type breakdown.
      </Text>

      <UsageSpendTenantDrawer
        isOpen={isDetailOpen}
        onClose={handleDetailClose}
        detail={selectedTenant}
        isLoading={isDetailLoading}
        periodKey={drawerPeriodKey}
        loadedPeriodKey={loadedPeriodKey}
        onPeriodChange={handleDrawerPeriodChange}
      />
    </VStack>
  );
};

export default UsageAndSpendTab;
