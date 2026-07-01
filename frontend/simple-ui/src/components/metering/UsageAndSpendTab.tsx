import React, { useMemo, useState, useCallback } from "react";
import { useQuery, useQueries } from "@tanstack/react-query";
import {
  Badge,
  Box,
  Center,
  Flex,
  FormControl,
  HStack,
  Progress,
  Select,
  Spinner,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
  useDisclosure,
} from "@chakra-ui/react";
import {
  fetchUsageSummary,
  fetchTenantUsageList,
  fetchTenantUsageById,
} from "../../services/usageSpendService";
import { fetchTiers } from "../../services/tierManagementService";
import { extractErrorInfo } from "../../utils/errorHandler";
import {
  MODEL_TASK_TYPE_LIST,
  formatModelTaskTypeLabel,
} from "../../config/constants";
import MeteringAsyncState from "./MeteringAsyncState";
import MeteringDataTable from "./MeteringDataTable";
import StandardModal from "../common/StandardModal";
import type {
  TenantUsageItem,
  TenantUsageDetail,
  UsageSummaryResponse,
} from "../../types/usageSpend";

interface UsageAndSpendTabProps {
  /** Platform admin tenant preview filter from the dashboard header. */
  scopeTenantId?: string | null;
  /** Signed-in tenant admin view — uses usage-tenant instead of admin list APIs. */
  isTenantView?: boolean;
  tenantId?: string | null;
  /** Bumped by the parent refresh control to invalidate queries. */
  refreshNonce?: number;
}

function matchesTierFilter(tierName: string, filterTier: string): boolean {
  if (!filterTier) return true;
  return tierName.trim().toLowerCase() === filterTier.trim().toLowerCase();
}

function matchesModelTaskType(value: string, filter: string): boolean {
  if (!filter) return true;
  return value.trim().toLowerCase() === filter.trim().toLowerCase();
}

function applyModelTaskTypeToDetail(
  detail: TenantUsageDetail,
  modelTaskType: string,
): TenantUsageDetail {
  if (!modelTaskType) return detail;
  const breakdown = (detail.breakdown ?? []).filter((item) =>
    matchesModelTaskType(item.modelTaskType, modelTaskType),
  );
  const match = breakdown[0];
  if (!match) {
    return {
      ...detail,
      consumptionToDate: 0,
      remainingQuota: detail.quotaLimit,
      breakdown: [],
    };
  }
  return {
    ...detail,
    consumptionToDate: match.consumptionToDate,
    remainingQuota: match.remainingQuota ?? detail.remainingQuota,
    quotaLimit: match.quotaLimit ?? detail.quotaLimit,
    quotaUnit: match.unit,
    breakdown,
  };
}

function summaryFromTenantDetail(detail: TenantUsageDetail): UsageSummaryResponse {
  const breakdown = detail.breakdown ?? [];
  const spendItems = breakdown.map((item) => ({
    modelTaskType: item.modelTaskType,
    unit: item.unit,
    consumption: item.consumptionToDate,
    spend: item.spend,
    percentage: 0,
  }));
  const breakdownSpend = spendItems.reduce((sum, item) => sum + item.spend, 0);
  const totalSpend = breakdownSpend > 0 ? breakdownSpend : detail.spendToDate;
  return {
    billingPeriod: new Date().toISOString().slice(0, 7),
    totalSpend,
    currency: detail.currency,
    spendByModelTaskType: spendItems.map((item) => ({
      ...item,
      percentage:
        totalSpend > 0 ? Number(((item.spend / totalSpend) * 100).toFixed(1)) : 0,
    })),
  };
}

function detailToListItem(detail: TenantUsageDetail): TenantUsageItem {
  const { breakdown: _breakdown, ...item } = detail;
  return item;
}

function filterTenantList(
  rows: TenantUsageItem[],
  filterTier: string,
): TenantUsageItem[] {
  return rows.filter((row) => matchesTierFilter(row.tier, filterTier));
}

function filterUsageSummary(
  summary: UsageSummaryResponse | undefined,
  filterTaskType: string,
): UsageSummaryResponse | undefined {
  if (!summary || !filterTaskType) return summary;
  const spendByModelTaskType = summary.spendByModelTaskType.filter((item) =>
    matchesModelTaskType(item.modelTaskType, filterTaskType),
  );
  const totalSpend = spendByModelTaskType.reduce((sum, item) => sum + item.spend, 0);
  return {
    ...summary,
    totalSpend,
    spendByModelTaskType: spendByModelTaskType.map((item) => ({
      ...item,
      percentage:
        totalSpend > 0 ? Number(((item.spend / totalSpend) * 100).toFixed(1)) : 0,
    })),
  };
}

const AVATAR_BG_COLORS = [
  "green.500",
  "blue.500",
  "purple.500",
  "teal.500",
  "orange.500",
];

function formatINR(amount: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount);
}

function formatQuota(value: number | null, unit: string): string {
  if (value == null) return "—";
  const parts = unit.trim().split(/\s+/);
  if (parts.length === 2) {
    return `${value.toLocaleString()}${parts[0]} ${parts[1].toLowerCase()}`;
  }
  return `${value.toLocaleString()} ${unit}`;
}

function getTenantInitials(name: string): string {
  const words = name.trim().split(/\s+/);
  if (words.length >= 2) return `${words[0][0]}${words[1][0]}`.toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

function getTenantAvatarBg(name: string): string {
  let sum = 0;
  for (let i = 0; i < name.length; i++) {
    sum += name.codePointAt(i) ?? 0;
  }
  return AVATAR_BG_COLORS[sum % AVATAR_BG_COLORS.length];
}

function remainingBudgetColor(remaining: number, limit: number): string {
  if (limit <= 0) return "gray.700";
  return remaining / limit < 0.35 ? "orange.500" : "gray.700";
}

function remainingQuotaColor(
  remaining: number | null,
  limit: number | null,
): string {
  if (remaining == null || limit == null || limit <= 0) return "gray.700";
  return remaining / limit < 0.35 ? "red.500" : "gray.700";
}

interface TenantRowProps {
  readonly row: TenantUsageItem;
  readonly onRowClick: (row: TenantUsageItem) => void;
}

function TenantRow({ row, onRowClick }: TenantRowProps) {
  return (
    <Tr
      cursor="pointer"
      _hover={{ bg: "blue.50" }}
      onClick={() => onRowClick(row)}
    >
      <Td>
        <HStack spacing={3}>
          <Center
            w={8}
            h={8}
            borderRadius="full"
            bg={getTenantAvatarBg(row.tenantName)}
            color="white"
            fontSize="xs"
            fontWeight="bold"
            flexShrink={0}
          >
            {getTenantInitials(row.tenantName)}
          </Center>
          <Text
            fontSize="sm"
            color="blue.500"
            fontWeight="medium"
          >
            {row.tenantName}
          </Text>
        </HStack>
      </Td>
      <Td>
        <Text
          fontSize="xs"
          fontWeight="semibold"
          textTransform="uppercase"
          color="gray.700"
          letterSpacing="wide"
        >
          {row.tier}
        </Text>
      </Td>
      <Td isNumeric fontSize="sm">
        {formatINR(row.budgetLimit)}
      </Td>
      <Td isNumeric fontSize="sm" fontWeight="medium">
        {formatINR(row.spendToDate)}
      </Td>
      <Td
        isNumeric
        fontSize="sm"
        fontWeight="medium"
        color={remainingBudgetColor(row.remainingBudget, row.budgetLimit)}
      >
        {formatINR(row.remainingBudget)}
      </Td>
      <Td isNumeric fontSize="sm">
        {formatQuota(row.quotaLimit, row.quotaUnit)}
      </Td>
      <Td isNumeric fontSize="sm" color="gray.600">
        {formatQuota(row.consumptionToDate, row.quotaUnit)}
      </Td>
      <Td
        isNumeric
        fontSize="sm"
        fontWeight="medium"
        color={remainingQuotaColor(row.remainingQuota, row.quotaLimit)}
      >
        {formatQuota(row.remainingQuota, row.quotaUnit)}
      </Td>
    </Tr>
  );
}

const UsageAndSpendTab: React.FC<UsageAndSpendTabProps> = ({
  scopeTenantId = null,
  isTenantView = false,
  tenantId = null,
  refreshNonce = 0,
}) => {
  const [filterTier, setFilterTier] = useState("");
  const [filterTaskType, setFilterTaskType] = useState("");
  const [selectedTenant, setSelectedTenant] =
    useState<TenantUsageDetail | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const {
    isOpen: isDetailOpen,
    onOpen: onDetailOpen,
    onClose: onDetailClose,
  } = useDisclosure();

  const scopedTenantId = isTenantView
    ? tenantId?.trim() || null
    : scopeTenantId?.trim() || null;
  const isScopedView = Boolean(scopedTenantId);

  const handleTenantClick = useCallback(
    async (row: TenantUsageItem) => {
      setIsDetailLoading(true);
      onDetailOpen();
      try {
        const detail = await fetchTenantUsageById(row.tenantId);
        setSelectedTenant(detail);
      } catch {
        setSelectedTenant(row);
      } finally {
        setIsDetailLoading(false);
      }
    },
    [onDetailOpen],
  );

  const summaryQuery = useQuery({
    queryKey: ["usage-summary", refreshNonce],
    queryFn: () => fetchUsageSummary(),
    enabled: !isScopedView,
    staleTime: 60_000,
    retry: 1,
  });

  const scopedTenantQuery = useQuery({
    queryKey: ["usage-tenant", scopedTenantId, refreshNonce],
    queryFn: () => fetchTenantUsageById(scopedTenantId!),
    enabled: isScopedView,
    staleTime: 60_000,
    retry: 1,
  });

  const tenantsQuery = useQuery({
    queryKey: ["usage-tenants", refreshNonce],
    queryFn: () => fetchTenantUsageList(),
    enabled: !isScopedView,
    staleTime: 60_000,
    retry: 1,
  });

  const tierFilteredTenantIds = useMemo(() => {
    if (isScopedView || !filterTaskType) return [];
    return (tenantsQuery.data?.data ?? [])
      .filter((row) => matchesTierFilter(row.tier, filterTier))
      .map((row) => row.tenantId);
  }, [isScopedView, filterTaskType, filterTier, tenantsQuery.data?.data]);

  const tenantBreakdownQueries = useQueries({
    queries: tierFilteredTenantIds.map((tenantId) => ({
      queryKey: ["usage-tenant-breakdown", tenantId, refreshNonce],
      queryFn: () => fetchTenantUsageById(tenantId),
      enabled: !isScopedView && !!filterTaskType,
      staleTime: 60_000,
      retry: 1,
    })),
  });

  const tiersQuery = useQuery({
    queryKey: ["tiers", refreshNonce],
    queryFn: () => fetchTiers(),
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const scopedTenantDetail = useMemo(() => {
    if (!scopedTenantQuery.data) return null;
    let detail = scopedTenantQuery.data;
    if (!matchesTierFilter(detail.tier, filterTier)) return null;
    detail = applyModelTaskTypeToDetail(detail, filterTaskType);
    return detail;
  }, [scopedTenantQuery.data, filterTier, filterTaskType]);

  const summaryData = isScopedView
    ? scopedTenantDetail
      ? summaryFromTenantDetail(scopedTenantDetail)
      : undefined
    : filterUsageSummary(summaryQuery.data, filterTaskType);

  const taskTypeOptions = useMemo(() => {
    const seen = new Set<string>();
    const options: string[] = [];
    const addOption = (taskType: string) => {
      const normalized = taskType.trim();
      if (!normalized || seen.has(normalized)) return;
      seen.add(normalized);
      options.push(normalized);
    };

    MODEL_TASK_TYPE_LIST.forEach(addOption);
    (summaryQuery.data?.spendByModelTaskType ?? []).forEach((item) =>
      addOption(item.modelTaskType),
    );
    (scopedTenantQuery.data?.breakdown ?? []).forEach((item) =>
      addOption(item.modelTaskType),
    );
    return options;
  }, [
    summaryQuery.data?.spendByModelTaskType,
    scopedTenantQuery.data?.breakdown,
  ]);

  const breakdownFilteredTenants = useMemo(() => {
    if (!filterTaskType) return [];
    return tenantBreakdownQueries
      .map((query) => query.data)
      .filter((detail): detail is TenantUsageDetail => Boolean(detail))
      .map((detail) => applyModelTaskTypeToDetail(detail, filterTaskType))
      .filter((detail) => (detail.breakdown?.length ?? 0) > 0)
      .map(detailToListItem);
  }, [filterTaskType, tenantBreakdownQueries]);

  const tenants = useMemo(() => {
    if (isScopedView) {
      if (
        !scopedTenantDetail ||
        (filterTaskType && (scopedTenantDetail.breakdown?.length ?? 0) === 0)
      ) {
        return [];
      }
      return [detailToListItem(scopedTenantDetail)];
    }
    if (filterTaskType) {
      return breakdownFilteredTenants;
    }
    return filterTenantList(tenantsQuery.data?.data ?? [], filterTier);
  }, [
    isScopedView,
    scopedTenantDetail,
    filterTaskType,
    filterTier,
    tenantsQuery.data?.data,
    breakdownFilteredTenants,
  ]);

  const tierNames = tiersQuery.data?.data?.map((t) => t.name) ?? [];

  const summaryError = isScopedView
    ? scopedTenantQuery.error
      ? extractErrorInfo(scopedTenantQuery.error).message
      : null
    : summaryQuery.error
      ? extractErrorInfo(summaryQuery.error).message
      : null;
  const tenantsError = isScopedView
    ? scopedTenantQuery.error
      ? extractErrorInfo(scopedTenantQuery.error).message
      : null
    : tenantsQuery.error
      ? extractErrorInfo(tenantsQuery.error).message
      : null;
  const isSummaryLoading = isScopedView
    ? scopedTenantQuery.isLoading
    : summaryQuery.isLoading;
  const isTenantsLoading = isScopedView
    ? scopedTenantQuery.isLoading
    : filterTaskType
      ? tenantsQuery.isLoading ||
        tenantBreakdownQueries.some((query) => query.isLoading)
      : tenantsQuery.isLoading;

  let spendByTaskContent: React.ReactNode;
  if (isSummaryLoading) {
    spendByTaskContent = (
      <Center h="100px">
        <Spinner color="blue.500" />
      </Center>
    );
  } else if (summaryError) {
    spendByTaskContent = (
      <Text fontSize="sm" color="red.500">
        {summaryError}
      </Text>
    );
  } else {
    spendByTaskContent = (
      <VStack align="stretch" spacing={4}>
        {(summaryData?.spendByModelTaskType ?? []).map((item) => (
          <Box key={item.modelTaskType}>
            <HStack justify="space-between" mb={1.5}>
              <HStack spacing={1} fontSize="sm">
                <Text fontWeight="bold">{item.modelTaskType}</Text>
                <Text color="gray.400">·</Text>
                <Text color="gray.500">
                  {formatQuota(item.consumption, item.unit)}
                </Text>
              </HStack>
              <HStack spacing={6} fontSize="sm">
                <Text fontWeight="medium">{formatINR(item.spend)}</Text>
                <Text color="gray.500" minW="44px" textAlign="right">
                  {item.percentage.toFixed(1)}%
                </Text>
              </HStack>
            </HStack>
            <Progress
              value={item.percentage}
              size="xs"
              colorScheme="blue"
              borderRadius="full"
              bg="blue.50"
            />
          </Box>
        ))}
      </VStack>
    );
  }

  const breakdownTotal =
    selectedTenant?.breakdown?.reduce((s, i) => s + i.spend, 0) ?? 0;

  let tenantDetailContent: React.ReactNode;
  if (isDetailLoading) {
    tenantDetailContent = (
      <Center py={8}>
        <Spinner color="blue.500" />
      </Center>
    );
  } else if (selectedTenant) {
    tenantDetailContent = (
      <VStack align="stretch" spacing={5}>
        <HStack spacing={3}>
          <Center
            w={10}
            h={10}
            borderRadius="full"
            bg={getTenantAvatarBg(selectedTenant.tenantName)}
            color="white"
            fontSize="sm"
            fontWeight="bold"
            flexShrink={0}
          >
            {getTenantInitials(selectedTenant.tenantName)}
          </Center>
          <Text fontWeight="semibold" fontSize="md">
            {selectedTenant.tenantName}
          </Text>
          <Badge colorScheme="blue" textTransform="uppercase" fontSize="xs">
            {selectedTenant.tier}
          </Badge>
        </HStack>

        <Box>
          <Text
            fontSize="xs"
            fontWeight="semibold"
            letterSpacing="widest"
            textTransform="uppercase"
            color="gray.500"
            mb={3}
          >
            Spend by Model Task Type
          </Text>
          {selectedTenant.breakdown && selectedTenant.breakdown.length > 0 ? (
            <Table size="sm" variant="simple">
              <Thead>
                <Tr>
                  <Th fontSize="xs" color="gray.500">
                    Model Task Type
                  </Th>
                  <Th fontSize="xs" color="gray.500" isNumeric>
                    Consumption
                  </Th>
                  <Th fontSize="xs" color="gray.500" isNumeric>
                    Spend (INR)
                  </Th>
                  <Th fontSize="xs" color="gray.500" isNumeric>
                    Share
                  </Th>
                </Tr>
              </Thead>
              <Tbody>
                {selectedTenant.breakdown.map((item) => (
                  <Tr key={item.modelTaskType}>
                    <Td>
                      <HStack spacing={2}>
                        <Box
                          w={2}
                          h={2}
                          borderRadius="full"
                          bg="blue.500"
                          flexShrink={0}
                        />
                        <Text fontSize="sm">{item.modelTaskType}</Text>
                      </HStack>
                    </Td>
                    <Td isNumeric fontSize="sm">
                      {formatQuota(item.consumptionToDate, item.unit)}
                    </Td>
                    <Td isNumeric fontSize="sm" fontWeight="medium">
                      {formatINR(item.spend)}
                    </Td>
                    <Td isNumeric fontSize="sm" color="gray.500">
                      {breakdownTotal > 0
                        ? `${((item.spend / breakdownTotal) * 100).toFixed(1)}%`
                        : "—"}
                    </Td>
                  </Tr>
                ))}
                <Tr borderTopWidth="2px" borderColor="gray.200">
                  <Td fontWeight="semibold" fontSize="sm">
                    Total
                  </Td>
                  <Td />
                  <Td isNumeric fontSize="sm" fontWeight="semibold">
                    {formatINR(breakdownTotal)}
                  </Td>
                  <Td />
                </Tr>
              </Tbody>
            </Table>
          ) : (
            <Text fontSize="sm" color="gray.400" py={4} textAlign="center">
              No spend breakdown available for this billing period.
            </Text>
          )}
        </Box>
      </VStack>
    );
  }

  return (
    <VStack align="stretch" spacing={6}>
      {/* Total Spend + Spend by Task Type */}
      <Flex gap={4} direction={{ base: "column", md: "row" }} align="stretch">
        {/* Left: Total Spend card */}
        <Box
          bgGradient="linear(135deg, blue.700, blue.900)"
          borderRadius="xl"
          p={8}
          color="white"
          flex={{ base: "none", md: "0 0 30%" }}
          minW={{ base: "full", md: "220px" }}
          display="flex"
          flexDirection="column"
          justifyContent="flex-end"
          minH="160px"
        >
          {isSummaryLoading ? (
            <Center flex={1}>
              <Spinner color="whiteAlpha.700" />
            </Center>
          ) : (
            <>
              <Text
                fontSize="xs"
                fontWeight="semibold"
                letterSpacing="widest"
                textTransform="uppercase"
                opacity={0.7}
                mb={3}
              >
                Total Spend
              </Text>
              <Text fontSize="4xl" fontWeight="bold" lineHeight="1">
                {summaryData ? formatINR(summaryData.totalSpend) : "—"}
              </Text>
            </>
          )}
        </Box>

        {/* Right: Spend by Model Task Type */}
        <Box
          flex={1}
          borderWidth="1px"
          borderColor="gray.200"
          borderRadius="xl"
          p={6}
          bg="white"
        >
          <Text
            fontSize="xs"
            fontWeight="semibold"
            letterSpacing="widest"
            textTransform="uppercase"
            color="gray.500"
            mb={4}
          >
            Spend by Model Task Type
          </Text>
          {spendByTaskContent}
        </Box>
      </Flex>

      {/* Filters */}
      <HStack spacing={4} flexWrap="wrap">
        <FormControl w={{ base: "full", sm: "220px" }}>
          <Select
            size="sm"
            value={filterTier}
            onChange={(e) => setFilterTier(e.target.value)}
            borderRadius="md"
          >
            <option value="">Filter by Tier — All Tiers</option>
            {tierNames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </Select>
        </FormControl>

        <FormControl w={{ base: "full", sm: "240px" }}>
          <Select
            size="sm"
            value={filterTaskType}
            onChange={(e) => setFilterTaskType(e.target.value)}
            borderRadius="md"
          >
            <option value="">Filter by Model Task Type — All</option>
            {taskTypeOptions.map((t) => (
              <option key={t} value={t}>
                {formatModelTaskTypeLabel(t)}
              </option>
            ))}
          </Select>
        </FormControl>
      </HStack>

      {/* Tenant usage table */}
      <MeteringAsyncState
        isLoading={isTenantsLoading}
        isEmpty={!isTenantsLoading && tenants.length === 0}
        errorMessage={tenantsError}
        emptyMessage={
          isScopedView
            ? "No usage data available for this tenant."
            : "No tenant usage data available."
        }
      >
        <MeteringDataTable>
          <Thead bg="gray.50">
            <Tr>
              <Th fontSize="xs" textTransform="uppercase" color="gray.500">
                Tenant
              </Th>
              <Th fontSize="xs" textTransform="uppercase" color="gray.500">
                Tier
              </Th>
              <Th
                fontSize="xs"
                textTransform="uppercase"
                color="gray.500"
                isNumeric
              >
                Budget Limit
              </Th>
              <Th
                fontSize="xs"
                textTransform="uppercase"
                color="gray.500"
                isNumeric
              >
                Spend to Date ↓
              </Th>
              <Th
                fontSize="xs"
                textTransform="uppercase"
                color="gray.500"
                isNumeric
              >
                Remaining Budget ↓
              </Th>
              <Th
                fontSize="xs"
                textTransform="uppercase"
                color="gray.500"
                isNumeric
              >
                Quota Limit
              </Th>
              <Th
                fontSize="xs"
                textTransform="uppercase"
                color="gray.500"
                isNumeric
              >
                Consumption to Date
              </Th>
              <Th
                fontSize="xs"
                textTransform="uppercase"
                color="gray.500"
                isNumeric
              >
                Remaining Quota ↓
              </Th>
            </Tr>
          </Thead>
          <Tbody>
            {tenants.map((row) => (
              <TenantRow
                key={row.tenantId}
                row={row}
                onRowClick={handleTenantClick}
              />
            ))}
          </Tbody>
        </MeteringDataTable>
      </MeteringAsyncState>

      {/* Tenant Spend Details Modal */}
      <StandardModal
        isOpen={isDetailOpen}
        onClose={onDetailClose}
        title="Tenant Spend Details"
        size="3xl"
        contentProps={{ minH: "60vh" }}
        bodyProps={{ py: 6, px: 8 }}
      >
        {tenantDetailContent}
      </StandardModal>
    </VStack>
  );
};

export default UsageAndSpendTab;
