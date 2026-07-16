import React, { useCallback, useState } from "react";
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
import { formatModelTaskTypeLabel } from "../../config/constants";
import { useInferenceTypes } from "../../hooks/useInferenceTypes";
import { useUsageAndSpendData } from "../../hooks/useUsageAndSpendData";
import {
  billingPeriodLabel,
  type BillingPeriodKey,
} from "../../utils/usageSpendHelpers";
import type { TenantUsageDetail, TenantUsageItem } from "../../types/usageSpend";
import SpendOverviewPanel from "./SpendOverviewPanel";
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
  const [filterTierId, setFilterTierId] = useState("");
  const [filterTaskType, setFilterTaskType] = useState("");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selectedTenant, setSelectedTenant] = useState<TenantUsageDetail | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const { isOpen: isDetailOpen, onOpen: onDetailOpen, onClose: onDetailClose } = useDisclosure();
  const { taskTypeNames } = useInferenceTypes();

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

  const subtitle = isTenantView
    ? orgName
      ? `${orgName} · ${METERING.USAGE_SPEND.TENANT_SUBTITLE_SUFFIX}`
      : METERING.USAGE_SPEND.TENANT_SUBTITLE_SUFFIX
    : METERING.USAGE_SPEND.ADOPTER_SUBTITLE;

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
      setIsDetailLoading(true);
      onDetailOpen();
      try {
        setSelectedTenant(await fetchTenantUsageById(row.tenantId, data.billingPeriod));
      } catch {
        setSelectedTenant(row);
      } finally {
        setIsDetailLoading(false);
      }
    },
    [onDetailOpen, data.billingPeriod],
  );

  return (
    <VStack align="stretch" spacing={5}>
      <Flex justify="space-between" align="flex-start" gap={6} flexWrap="wrap">
        <Box>
          <Text fontSize="26px" fontWeight="semibold" lineHeight="1.2" mb={1}>
            {METERING.USAGE_SPEND.TITLE}
          </Text>
          <Text fontSize="14px" color="gray.600">
            {subtitle}
          </Text>
        </Box>
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
          >
            <option value="current">{METERING.USAGE_SPEND.CURRENT_MONTH}</option>
            <option value="last">{METERING.USAGE_SPEND.LAST_MONTH}</option>
          </Select>
        </FormControl>
      </Flex>

      <SpendOverviewPanel
        summary={data.summaryData}
        isLoading={data.isSummaryLoading}
        error={data.summaryError}
        currency={data.currency}
        spendChangePercent={data.spendChangePercent}
        tenantDetail={isTenantView ? tenantDetail : null}
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

      {!isTenantView ? (
        <>
          <UsageSpendTenantTable
            tenants={data.tenants}
            isLoading={data.isTenantsLoading}
            errorMessage={data.tenantsError}
            emptyMessage={
              data.isScoped
                ? "No usage data available for this tenant."
                : "No tenant usage data available."
            }
            filterTaskType={filterTaskType}
            sortOrder={sortOrder}
            expanded={expanded}
            taskColorByType={data.taskColorByType}
            onToggleSort={() => setSortOrder((o) => (o === "desc" ? "asc" : "desc"))}
            onToggleExpand={toggleExpand}
            onTenantClick={handleTenantClick}
          />

          <Text fontSize="12px" color="gray.500" lineHeight="1.6">
            Spend is a sortable column. Budget shows utilization against the allocated limit. Units
            follow each service&apos;s metering definition. Tier and task type filters apply to the
            table; expand a tenant to see task-type breakdown, grouped by tier when the tenant
            changed tiers mid-period.
          </Text>

          <UsageSpendTenantDrawer
            isOpen={isDetailOpen}
            onClose={onDetailClose}
            detail={selectedTenant}
            isLoading={isDetailLoading}
            periodLabel={billingPeriodLabel(periodKey)}
          />
        </>
      ) : null}
    </VStack>
  );
};

export default UsageAndSpendTab;
