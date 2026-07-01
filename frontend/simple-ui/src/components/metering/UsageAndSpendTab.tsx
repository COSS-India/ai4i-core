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
import { parseError } from "../../utils/errorHandler";
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
  readonly scopeTenantId?: string | null;
  readonly isTenantView?: boolean;
  readonly tenantId?: string | null;
  readonly refreshNonce?: number;
}

const AVATAR_BG = ["green.500", "blue.500", "purple.500", "teal.500", "orange.500"];
const STALE_MS = 60_000;

const formatINR = (n: number) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n);

const formatQuota = (value: number | null, unit: string) => {
  if (value == null) return "—";
  const parts = unit.trim().split(/\s+/);
  if (parts.length === 2) return `${value.toLocaleString()}${parts[0]} ${parts[1].toLowerCase()}`;
  return `${value.toLocaleString()} ${unit}`;
};

const eqCi = (value: string, filter: string) =>
  !filter || value.trim().toLowerCase() === filter.trim().toLowerCase();

const tenantInitials = (name: string) => {
  const words = name.trim().split(/\s+/);
  return words.length >= 2 ? `${words[0][0]}${words[1][0]}`.toUpperCase() : name.slice(0, 2).toUpperCase();
};

const tenantAvatarBg = (name: string) => {
  let sum = 0;
  for (let i = 0; i < name.length; i++) sum += name.codePointAt(i) ?? 0;
  return AVATAR_BG[sum % AVATAR_BG.length];
};

const spendPct = (spend: number, total: number) =>
  total > 0 ? Number(((spend / total) * 100).toFixed(1)) : 0;

const applyTaskTypeFilter = (detail: TenantUsageDetail, taskType: string): TenantUsageDetail => {
  if (!taskType) return detail;
  const breakdown = (detail.breakdown ?? []).filter((i) => eqCi(i.modelTaskType, taskType));
  const match = breakdown[0];
  if (!match) return { ...detail, consumptionToDate: 0, remainingQuota: detail.quotaLimit, breakdown: [] };
  return {
    ...detail,
    consumptionToDate: match.consumptionToDate,
    remainingQuota: match.remainingQuota ?? detail.remainingQuota,
    quotaLimit: match.quotaLimit ?? detail.quotaLimit,
    quotaUnit: match.unit,
    breakdown,
  };
};

const summaryFromDetail = (detail: TenantUsageDetail): UsageSummaryResponse => {
  const items = (detail.breakdown ?? []).map((i) => ({
    modelTaskType: i.modelTaskType,
    unit: i.unit,
    consumption: i.consumptionToDate,
    spend: i.spend,
    percentage: 0,
  }));
  const total = items.reduce((s, i) => s + i.spend, 0) || detail.spendToDate;
  return {
    billingPeriod: new Date().toISOString().slice(0, 7),
    totalSpend: total,
    currency: detail.currency,
    spendByModelTaskType: items.map((i) => ({ ...i, percentage: spendPct(i.spend, total) })),
  };
};

const filterSummary = (summary: UsageSummaryResponse | undefined, taskType: string) => {
  if (!summary || !taskType) return summary;
  const spendByModelTaskType = summary.spendByModelTaskType.filter((i) => eqCi(i.modelTaskType, taskType));
  const totalSpend = spendByModelTaskType.reduce((s, i) => s + i.spend, 0);
  return {
    ...summary,
    totalSpend,
    spendByModelTaskType: spendByModelTaskType.map((i) => ({ ...i, percentage: spendPct(i.spend, totalSpend) })),
  };
};

const buildTaskTypeOptions = (
  summary?: UsageSummaryResponse["spendByModelTaskType"],
  breakdown?: TenantUsageDetail["breakdown"],
) => {
  const seen = new Set<string>();
  const out: string[] = [];
  const add = (t: string) => {
    const n = t.trim();
    if (n && !seen.has(n)) { seen.add(n); out.push(n); }
  };
  MODEL_TASK_TYPE_LIST.forEach(add);
  (summary ?? []).forEach((i) => add(i.modelTaskType));
  (breakdown ?? []).forEach((i) => add(i.modelTaskType));
  return out;
};

function useUsageAndSpendData(
  scopeTenantId: string | null,
  isTenantView: boolean,
  tenantId: string | null,
  refreshNonce: number,
  filterTier: string,
  filterTaskType: string,
) {
  const scopedId = (isTenantView ? tenantId : scopeTenantId)?.trim() || null;
  const isScoped = Boolean(scopedId);

  const summaryQuery = useQuery({
    queryKey: ["usage-summary", refreshNonce],
    queryFn: () => fetchUsageSummary(),
    enabled: !isScoped,
    staleTime: STALE_MS,
    retry: 1,
  });

  const scopedQuery = useQuery({
    queryKey: ["usage-tenant", scopedId, refreshNonce],
    queryFn: () => {
      if (!scopedId) throw new Error("Tenant id is required");
      return fetchTenantUsageById(scopedId);
    },
    enabled: isScoped,
    staleTime: STALE_MS,
    retry: 1,
  });

  const tenantsQuery = useQuery({
    queryKey: ["usage-tenants", refreshNonce],
    queryFn: () => fetchTenantUsageList(),
    enabled: !isScoped,
    staleTime: STALE_MS,
    retry: 1,
  });

  const tiersQuery = useQuery({
    queryKey: ["tiers", refreshNonce],
    queryFn: () => fetchTiers(),
    staleTime: 5 * STALE_MS,
    retry: 1,
  });

  const breakdownIds = useMemo(() => {
    if (isScoped || !filterTaskType) return [];
    return (tenantsQuery.data?.data ?? [])
      .filter((r) => eqCi(r.tier, filterTier))
      .map((r) => r.tenantId);
  }, [isScoped, filterTaskType, filterTier, tenantsQuery.data?.data]);

  const breakdownQueries = useQueries({
    queries: breakdownIds.map((id) => ({
      queryKey: ["usage-tenant-breakdown", id, refreshNonce],
      queryFn: () => fetchTenantUsageById(id),
      enabled: !isScoped && Boolean(filterTaskType),
      staleTime: STALE_MS,
      retry: 1,
    })),
  });

  const scopedDetail = useMemo(() => {
    if (!scopedQuery.data || !eqCi(scopedQuery.data.tier, filterTier)) return null;
    return applyTaskTypeFilter(scopedQuery.data, filterTaskType);
  }, [scopedQuery.data, filterTier, filterTaskType]);

  const tenants = useMemo((): TenantUsageItem[] => {
    if (isScoped) {
      if (!scopedDetail || (filterTaskType && !(scopedDetail.breakdown?.length))) return [];
      const { breakdown: _, ...item } = scopedDetail;
      return [item];
    }
    if (filterTaskType) {
      return breakdownQueries
        .map((q) => q.data)
        .filter((d): d is TenantUsageDetail => d != null)
        .map((d) => applyTaskTypeFilter(d, filterTaskType))
        .filter((d) => (d.breakdown?.length ?? 0) > 0)
        .map(({ breakdown: _, ...item }) => item);
    }
    return (tenantsQuery.data?.data ?? []).filter((r) => eqCi(r.tier, filterTier));
  }, [isScoped, scopedDetail, filterTaskType, breakdownQueries, tenantsQuery.data?.data, filterTier]);

  let summaryData: UsageSummaryResponse | undefined;
  if (isScoped) summaryData = scopedDetail ? summaryFromDetail(scopedDetail) : undefined;
  else summaryData = filterSummary(summaryQuery.data, filterTaskType);

  const errMsg = (e: unknown) => (e ? parseError(e).message : null);
  const scopedErr = scopedQuery.error;
  const platformSummaryErr = summaryQuery.error;
  const platformTenantsErr = tenantsQuery.error;

  let summaryError: string | null;
  let tenantsError: string | null;
  let isSummaryLoading: boolean;
  let isTenantsLoading: boolean;

  if (isScoped) {
    summaryError = errMsg(scopedErr);
    tenantsError = errMsg(scopedErr);
    isSummaryLoading = scopedQuery.isLoading;
    isTenantsLoading = scopedQuery.isLoading;
  } else {
    summaryError = errMsg(platformSummaryErr);
    tenantsError = errMsg(platformTenantsErr);
    isSummaryLoading = summaryQuery.isLoading;
    isTenantsLoading = filterTaskType
      ? tenantsQuery.isLoading || breakdownQueries.some((q) => q.isLoading)
      : tenantsQuery.isLoading;
  }

  return {
    summaryData,
    taskTypeOptions: buildTaskTypeOptions(summaryQuery.data?.spendByModelTaskType, scopedQuery.data?.breakdown),
    tierNames: tiersQuery.data?.data?.map((t) => t.name) ?? [],
    tenants,
    summaryError,
    tenantsError,
    isSummaryLoading,
    isTenantsLoading,
    emptyMessage: isScoped ? "No usage data available for this tenant." : "No tenant usage data available.",
  };
}

const UsageAndSpendTab: React.FC<UsageAndSpendTabProps> = ({
  scopeTenantId = null,
  isTenantView = false,
  tenantId = null,
  refreshNonce = 0,
}) => {
  const [filterTier, setFilterTier] = useState("");
  const [filterTaskType, setFilterTaskType] = useState("");
  const [selectedTenant, setSelectedTenant] = useState<TenantUsageDetail | null>(null);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const { isOpen: isDetailOpen, onOpen: onDetailOpen, onClose: onDetailClose } = useDisclosure();

  const data = useUsageAndSpendData(
    scopeTenantId,
    isTenantView,
    tenantId,
    refreshNonce,
    filterTier,
    filterTaskType,
  );

  const handleTenantClick = useCallback(async (row: TenantUsageItem) => {
    setIsDetailLoading(true);
    onDetailOpen();
    try {
      setSelectedTenant(await fetchTenantUsageById(row.tenantId));
    } catch {
      setSelectedTenant(row);
    } finally {
      setIsDetailLoading(false);
    }
  }, [onDetailOpen]);

  const breakdownTotal = selectedTenant?.breakdown?.reduce((s, i) => s + i.spend, 0) ?? 0;
  const budgetColor = (r: number, l: number) => (l <= 0 || r / l >= 0.35 ? "gray.700" : "orange.500");
  const quotaColor = (r: number | null, l: number | null) =>
    r == null || l == null || l <= 0 || r / l >= 0.35 ? "gray.700" : "red.500";

  return (
    <VStack align="stretch" spacing={6}>
      <Flex gap={4} direction={{ base: "column", md: "row" }} align="stretch">
        <Box
          bgGradient="linear(135deg, blue.700, blue.900)"
          borderRadius="xl" p={8} color="white"
          flex={{ base: "none", md: "0 0 30%" }} minW={{ base: "full", md: "220px" }}
          display="flex" flexDirection="column" justifyContent="flex-end" minH="160px"
        >
          {data.isSummaryLoading ? (
            <Center flex={1}><Spinner color="whiteAlpha.700" /></Center>
          ) : (
            <>
              <Text fontSize="xs" fontWeight="semibold" letterSpacing="widest" textTransform="uppercase" opacity={0.7} mb={3}>
                Total Spend
              </Text>
              <Text fontSize="4xl" fontWeight="bold" lineHeight="1">
                {data.summaryData ? formatINR(data.summaryData.totalSpend) : "—"}
              </Text>
            </>
          )}
        </Box>
        <Box flex={1} borderWidth="1px" borderColor="gray.200" borderRadius="xl" p={6} bg="white">
          <Text fontSize="xs" fontWeight="semibold" letterSpacing="widest" textTransform="uppercase" color="gray.500" mb={4}>
            Spend by Model Task Type
          </Text>
          {data.isSummaryLoading ? (
            <Center h="100px"><Spinner color="blue.500" /></Center>
          ) : data.summaryError ? (
            <Text fontSize="sm" color="red.500">{data.summaryError}</Text>
          ) : (
            <VStack align="stretch" spacing={4}>
              {(data.summaryData?.spendByModelTaskType ?? []).map((item) => (
                <Box key={item.modelTaskType}>
                  <HStack justify="space-between" mb={1.5}>
                    <HStack spacing={1} fontSize="sm">
                      <Text fontWeight="bold">{item.modelTaskType}</Text>
                      <Text color="gray.400">·</Text>
                      <Text color="gray.500">{formatQuota(item.consumption, item.unit)}</Text>
                    </HStack>
                    <HStack spacing={6} fontSize="sm">
                      <Text fontWeight="medium">{formatINR(item.spend)}</Text>
                      <Text color="gray.500" minW="44px" textAlign="right">{item.percentage.toFixed(1)}%</Text>
                    </HStack>
                  </HStack>
                  <Progress value={item.percentage} size="xs" colorScheme="blue" borderRadius="full" bg="blue.50" />
                </Box>
              ))}
            </VStack>
          )}
        </Box>
      </Flex>

      <HStack spacing={4} flexWrap="wrap">
        <FormControl w={{ base: "full", sm: "220px" }}>
          <Select size="sm" value={filterTier} onChange={(e) => setFilterTier(e.target.value)} borderRadius="md">
            <option value="">Filter by Tier — All Tiers</option>
            {data.tierNames.map((name) => <option key={name} value={name}>{name}</option>)}
          </Select>
        </FormControl>
        <FormControl w={{ base: "full", sm: "240px" }}>
          <Select size="sm" value={filterTaskType} onChange={(e) => setFilterTaskType(e.target.value)} borderRadius="md">
            <option value="">Filter by Model Task Type — All</option>
            {data.taskTypeOptions.map((t) => (
              <option key={t} value={t}>{formatModelTaskTypeLabel(t)}</option>
            ))}
          </Select>
        </FormControl>
      </HStack>

      <MeteringAsyncState
        isLoading={data.isTenantsLoading}
        isEmpty={!data.isTenantsLoading && data.tenants.length === 0}
        errorMessage={data.tenantsError}
        emptyMessage={data.emptyMessage}
      >
        <MeteringDataTable>
          <Thead bg="gray.50">
            <Tr>
              {["Tenant", "Tier", "Budget Limit", "Spend to Date ↓", "Remaining Budget ↓", "Quota Limit", "Consumption to Date", "Remaining Quota ↓"].map((h) => (
                <Th key={h} fontSize="xs" textTransform="uppercase" color="gray.500" isNumeric={h !== "Tenant" && h !== "Tier"}>{h}</Th>
              ))}
            </Tr>
          </Thead>
          <Tbody>
            {data.tenants.map((row) => (
              <Tr key={row.tenantId} cursor="pointer" _hover={{ bg: "blue.50" }} onClick={() => handleTenantClick(row)}>
                <Td>
                  <HStack spacing={3}>
                    <Center w={8} h={8} borderRadius="full" bg={tenantAvatarBg(row.tenantName)} color="white" fontSize="xs" fontWeight="bold" flexShrink={0}>
                      {tenantInitials(row.tenantName)}
                    </Center>
                    <Text fontSize="sm" color="blue.500" fontWeight="medium">{row.tenantName}</Text>
                  </HStack>
                </Td>
                <Td><Text fontSize="xs" fontWeight="semibold" textTransform="uppercase" color="gray.700" letterSpacing="wide">{row.tier}</Text></Td>
                <Td isNumeric fontSize="sm">{formatINR(row.budgetLimit)}</Td>
                <Td isNumeric fontSize="sm" fontWeight="medium">{formatINR(row.spendToDate)}</Td>
                <Td isNumeric fontSize="sm" fontWeight="medium" color={budgetColor(row.remainingBudget, row.budgetLimit)}>{formatINR(row.remainingBudget)}</Td>
                <Td isNumeric fontSize="sm">{formatQuota(row.quotaLimit, row.quotaUnit)}</Td>
                <Td isNumeric fontSize="sm" color="gray.600">{formatQuota(row.consumptionToDate, row.quotaUnit)}</Td>
                <Td isNumeric fontSize="sm" fontWeight="medium" color={quotaColor(row.remainingQuota, row.quotaLimit)}>{formatQuota(row.remainingQuota, row.quotaUnit)}</Td>
              </Tr>
            ))}
          </Tbody>
        </MeteringDataTable>
      </MeteringAsyncState>

      <StandardModal isOpen={isDetailOpen} onClose={onDetailClose} title="Tenant Spend Details" size="3xl" contentProps={{ minH: "60vh" }} bodyProps={{ py: 6, px: 8 }}>
        {isDetailLoading ? (
          <Center py={8}><Spinner color="blue.500" /></Center>
        ) : selectedTenant ? (
          <VStack align="stretch" spacing={5}>
            <HStack spacing={3}>
              <Center w={10} h={10} borderRadius="full" bg={tenantAvatarBg(selectedTenant.tenantName)} color="white" fontSize="sm" fontWeight="bold" flexShrink={0}>
                {tenantInitials(selectedTenant.tenantName)}
              </Center>
              <Text fontWeight="semibold" fontSize="md">{selectedTenant.tenantName}</Text>
              <Badge colorScheme="blue" textTransform="uppercase" fontSize="xs">{selectedTenant.tier}</Badge>
            </HStack>
            <Box>
              <Text fontSize="xs" fontWeight="semibold" letterSpacing="widest" textTransform="uppercase" color="gray.500" mb={3}>
                Spend by Model Task Type
              </Text>
              {selectedTenant.breakdown?.length ? (
                <Table size="sm" variant="simple">
                  <Thead>
                    <Tr>
                      {["Model Task Type", "Consumption", "Spend (INR)", "Share"].map((h, i) => (
                        <Th key={h} fontSize="xs" color="gray.500" isNumeric={i > 0}>{h}</Th>
                      ))}
                    </Tr>
                  </Thead>
                  <Tbody>
                    {selectedTenant.breakdown.map((item) => (
                      <Tr key={item.modelTaskType}>
                        <Td><HStack spacing={2}><Box w={2} h={2} borderRadius="full" bg="blue.500" flexShrink={0} /><Text fontSize="sm">{item.modelTaskType}</Text></HStack></Td>
                        <Td isNumeric fontSize="sm">{formatQuota(item.consumptionToDate, item.unit)}</Td>
                        <Td isNumeric fontSize="sm" fontWeight="medium">{formatINR(item.spend)}</Td>
                        <Td isNumeric fontSize="sm" color="gray.500">{breakdownTotal > 0 ? `${spendPct(item.spend, breakdownTotal)}%` : "—"}</Td>
                      </Tr>
                    ))}
                    <Tr borderTopWidth="2px" borderColor="gray.200">
                      <Td fontWeight="semibold" fontSize="sm">Total</Td><Td /><Td isNumeric fontSize="sm" fontWeight="semibold">{formatINR(breakdownTotal)}</Td><Td />
                    </Tr>
                  </Tbody>
                </Table>
              ) : (
                <Text fontSize="sm" color="gray.400" py={4} textAlign="center">No spend breakdown available for this billing period.</Text>
              )}
            </Box>
          </VStack>
        ) : null}
      </StandardModal>
    </VStack>
  );
};

export default UsageAndSpendTab;
