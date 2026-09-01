import React, { useCallback, useRef, useState } from "react";
import {
  Box,
  Flex,
  HStack,
  Select,
  Text,
  VStack,
  useDisclosure,
} from "@chakra-ui/react";
import { METERING } from "../../config/meteringConstants";
import { fetchTenantUsageById } from "../../services/usageSpendService";
import { INSTITUTION } from "../../config/constants";
import { useInferenceTypes } from "../../hooks/useInferenceTypes";
import { useUsageAndSpendData } from "../../hooks/useUsageAndSpendData";
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
  const [filterTierId, setFilterTierId] = useState("");
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
    filterTierId,
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
    [onDetailOpen, data.billingPeriod, enabledTaskTypesParam],
  );

  const handleDetailClose = useCallback(() => {
    detailRequestIdRef.current += 1;
    onDetailClose();
    setSelectedTenant(null);
    setIsDetailLoading(false);
  }, [onDetailClose]);

  return (
    <VStack align="stretch" spacing={5}>
      {isTenantView && tenantDetail ? (
        <Flex justify="space-between" align="center" gap={6} flexWrap="wrap">
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
          <TierBadge label={tenantDetail.tier} />
        </Flex>
      ) : null}

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
        expanded={expanded}
        onToggleExpand={toggleExpand}
        onTenantClick={handleTenantClick}
      />

      <Text fontSize="12px" color="gray.500" lineHeight="1.6">
        Table columns are sortable. Budget shows utilization against the allocated limit.
        When an institution changed tiers mid-period, expand it to see spend split by tier.
        Open an institution for the full model task-type breakdown.
      </Text>

      <UsageSpendTenantDrawer
        isOpen={isDetailOpen}
        onClose={handleDetailClose}
        detail={selectedTenant}
        isLoading={isDetailLoading}
      />
    </VStack>
  );
};

export default UsageAndSpendTab;
