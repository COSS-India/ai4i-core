import React, { useState, useCallback } from "react";
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
import { fetchTenantUsageById } from "../../services/usageSpendService";
import { formatModelTaskTypeLabel } from "../../config/constants";
import MeteringAsyncState from "./MeteringAsyncState";
import MeteringDataTable from "./MeteringDataTable";
import StandardModal from "../common/StandardModal";
import { useUsageAndSpendData } from "./useUsageAndSpendData";
import type {
  TenantUsageItem,
  TenantUsageDetail,
  UsageSummaryResponse,
} from "../../types/usageSpend";

interface UsageAndSpendTabProps {
  scopeTenantId?: string | null;
  isTenantView?: boolean;
  tenantId?: string | null;
  refreshNonce?: number;
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
          <Text fontSize="sm" color="blue.500" fontWeight="medium">
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

interface SpendByTaskTypePanelProps {
  readonly isLoading: boolean;
  readonly errorMessage: string | null;
  readonly summaryData: UsageSummaryResponse | undefined;
}

function SpendByTaskTypePanel({
  isLoading,
  errorMessage,
  summaryData,
}: SpendByTaskTypePanelProps) {
  if (isLoading) {
    return (
      <Center h="100px">
        <Spinner color="blue.500" />
      </Center>
    );
  }

  if (errorMessage) {
    return (
      <Text fontSize="sm" color="red.500">
        {errorMessage}
      </Text>
    );
  }

  return (
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

interface TenantSpendDetailBodyProps {
  readonly isLoading: boolean;
  readonly tenant: TenantUsageDetail | null;
}

function TenantSpendDetailBody({ isLoading, tenant }: TenantSpendDetailBodyProps) {
  if (isLoading) {
    return (
      <Center py={8}>
        <Spinner color="blue.500" />
      </Center>
    );
  }

  if (!tenant) return null;

  const breakdownTotal =
    tenant.breakdown?.reduce((sum, item) => sum + item.spend, 0) ?? 0;

  return (
    <VStack align="stretch" spacing={5}>
      <HStack spacing={3}>
        <Center
          w={10}
          h={10}
          borderRadius="full"
          bg={getTenantAvatarBg(tenant.tenantName)}
          color="white"
          fontSize="sm"
          fontWeight="bold"
          flexShrink={0}
        >
          {getTenantInitials(tenant.tenantName)}
        </Center>
        <Text fontWeight="semibold" fontSize="md">
          {tenant.tenantName}
        </Text>
        <Badge colorScheme="blue" textTransform="uppercase" fontSize="xs">
          {tenant.tier}
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
        {tenant.breakdown && tenant.breakdown.length > 0 ? (
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
              {tenant.breakdown.map((item) => (
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

  const {
    summaryData,
    taskTypeOptions,
    tierNames,
    tenants,
    summaryError,
    tenantsError,
    isSummaryLoading,
    isTenantsLoading,
    emptyMessage,
  } = useUsageAndSpendData({
    scopeTenantId,
    isTenantView,
    tenantId,
    refreshNonce,
    filterTier,
    filterTaskType,
  });

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

  return (
    <VStack align="stretch" spacing={6}>
      <Flex gap={4} direction={{ base: "column", md: "row" }} align="stretch">
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
          <SpendByTaskTypePanel
            isLoading={isSummaryLoading}
            errorMessage={summaryError}
            summaryData={summaryData}
          />
        </Box>
      </Flex>

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

      <MeteringAsyncState
        isLoading={isTenantsLoading}
        isEmpty={!isTenantsLoading && tenants.length === 0}
        errorMessage={tenantsError}
        emptyMessage={emptyMessage}
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

      <StandardModal
        isOpen={isDetailOpen}
        onClose={onDetailClose}
        title="Tenant Spend Details"
        size="3xl"
        contentProps={{ minH: "60vh" }}
        bodyProps={{ py: 6, px: 8 }}
      >
        <TenantSpendDetailBody
          isLoading={isDetailLoading}
          tenant={selectedTenant}
        />
      </StandardModal>
    </VStack>
  );
};

export default UsageAndSpendTab;
