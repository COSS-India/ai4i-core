import {
  Badge,
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Heading,
  HStack,
  Input,
  Progress,
  SimpleGrid,
  Stat,
  StatLabel,
  StatNumber,
  Table,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
} from "@chakra-ui/react";
import React from "react";
import type { TenantUsageDetailResponse } from "../../services/usageService";
import { tierModelsLabel } from "../../utils/planGrouping";

function formatIn(n: number): string {
  return Number(n || 0).toLocaleString("en-IN");
}

function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const ms = Date.now() - d.getTime();
  const hours = Math.floor(ms / 3600000);
  if (hours < 1) return "< 1 hr ago";
  if (hours < 48) return `${hours} hrs ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function statusBadgeProps(status: string): { bg: string; color: string } {
  const u = status.toUpperCase();
  if (u === "BLOCKED") return { bg: "red.500", color: "white" };
  if (u === "NEAR LIMIT" || u === "NEAR_LIMIT") return { bg: "orange.400", color: "white" };
  return { bg: "green.500", color: "white" };
}

export interface TenantUsageDetailViewProps {
  data: TenantUsageDetailResponse;
  showBack?: boolean;
  onBack?: () => void;
  /** Wallet top-up (tenant’s own dashboard) */
  showTopUp?: boolean;
  topUpValue?: string;
  onTopUpChange?: (v: string) => void;
  onTopUpSubmit?: () => void;
}

export default function TenantUsageDetailView({
  data,
  showBack = false,
  onBack,
  showTopUp = false,
  topUpValue = "100",
  onTopUpChange,
  onTopUpSubmit,
}: TenantUsageDetailViewProps) {
  const w = data.wallet;
  const util = w.utilization_percent ?? 0;

  return (
    <VStack align="stretch" spacing={6}>
      {showBack && onBack && (
        <Button variant="ghost" alignSelf="flex-start" size="sm" onClick={onBack}>
          ← Back to dashboard
        </Button>
      )}
      <Box>
        <Heading size="md">{data.plan?.plan_name || data.tenant_name}</Heading>
        {data.plan?.plan_name && (
          <Text fontSize="sm" color="gray.600" mt={1}>
            {data.tenant_name}
          </Text>
        )}
        <HStack mt={2} flexWrap="wrap" gap={2} align="center">
          <Text fontSize="sm" color="gray.700" fontWeight="medium">
            {tierModelsLabel(data.plan?.tier)}
          </Text>
          <Badge {...statusBadgeProps(data.status)}>{data.status}</Badge>
        </HStack>
      </Box>

      <SimpleGrid columns={{ base: 1, sm: 2, md: 4 }} spacing={4}>
        <Card variant="outline">
          <CardBody>
            <Stat>
              <StatLabel>Total requests</StatLabel>
              <StatNumber fontSize="2xl">{formatIn(data.total_requests)}</StatNumber>
            </Stat>
          </CardBody>
        </Card>
        <Card variant="outline">
          <CardBody>
            <Stat>
              <StatLabel>Plan budget</StatLabel>
              <StatNumber fontSize="2xl">₹{formatIn(w.total_plan_cost)}</StatNumber>
            </Stat>
          </CardBody>
        </Card>
        <Card variant="outline">
          <CardBody>
            <Stat>
              <StatLabel>Cost used</StatLabel>
              <StatNumber fontSize="2xl">₹{formatIn(w.total_used)}</StatNumber>
            </Stat>
          </CardBody>
        </Card>
        <Card variant="outline">
          <CardBody>
            <Stat>
              <StatLabel>Remaining</StatLabel>
              <StatNumber fontSize="2xl">₹{formatIn(w.remaining)}</StatNumber>
            </Stat>
            <Progress
              mt={3}
              value={Math.min(100, util)}
              size="sm"
              colorScheme={util > 80 ? "orange" : "blue"}
              borderRadius="md"
            />
            <Text fontSize="xs" color="gray.600" mt={1}>
              {util}% of budget used
            </Text>
          </CardBody>
        </Card>
      </SimpleGrid>

      {showTopUp && onTopUpChange && onTopUpSubmit && (
        <Card variant="outline">
          <CardHeader pb={2}>
            <Heading size="sm">Top up wallet</Heading>
          </CardHeader>
          <CardBody pt={0}>
            <HStack>
              <Input
                type="number"
                value={topUpValue}
                onChange={(e) => onTopUpChange(e.target.value)}
                maxW="200px"
                bg="white"
              />
              <Button colorScheme="blue" size="sm" onClick={onTopUpSubmit}>
                Top up
              </Button>
            </HStack>
          </CardBody>
        </Card>
      )}

      <Card variant="outline">
        <CardHeader>
          <Heading size="sm">Service quota usage</Heading>
        </CardHeader>
        <CardBody pt={0}>
          <VStack align="stretch" spacing={4}>
            {(data.service_usage || []).map((s) => {
              const pct = s.quota_percent || 0;
              return (
                <Box key={`${s.service_name}-${s.unit_type}`}>
                  <HStack justify="space-between" mb={1}>
                    <Text fontSize="sm" fontWeight="medium">
                      {s.service_name} ({s.unit_type})
                    </Text>
                    <Text fontSize="sm" color="gray.600">
                      {formatIn(s.units_used)} / {formatIn(s.quota_limit)} ({pct.toFixed(0)}%)
                    </Text>
                  </HStack>
                  <Progress
                    value={Math.min(100, pct)}
                    size="sm"
                    borderRadius="md"
                    colorScheme={pct > 80 ? "orange" : pct >= 50 ? "yellow" : "blue"}
                  />
                </Box>
              );
            })}
            {(!data.service_usage || data.service_usage.length === 0) && (
              <Text fontSize="sm" color="gray.600">
                No service usage yet.
              </Text>
            )}
          </VStack>
        </CardBody>
      </Card>

      <Card variant="outline">
        <CardHeader>
          <Heading size="sm">Usage breakdown</Heading>
        </CardHeader>
        <CardBody pt={0}>
          <Table size="sm" variant="simple">
            <Thead>
              <Tr>
                <Th>Service</Th>
                <Th isNumeric>Units used</Th>
                <Th>Unit type</Th>
                <Th isNumeric>Rate (₹)</Th>
                <Th isNumeric>Cost (₹)</Th>
              </Tr>
            </Thead>
            <Tbody>
              {(data.service_usage || []).map((s) => (
                <Tr key={`tb-${s.service_name}`}>
                  <Td>{s.service_name}</Td>
                  <Td isNumeric>{formatIn(s.units_used)}</Td>
                  <Td>{s.unit_type}</Td>
                  <Td isNumeric>{s.rate_per_unit}</Td>
                  <Td isNumeric>{formatIn(s.total_cost)}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </CardBody>
      </Card>

      <Card variant="outline">
        <CardHeader>
          <Heading size="sm">API key breakdown</Heading>
        </CardHeader>
        <CardBody pt={0}>
          <Table size="sm" variant="simple">
            <Thead>
              <Tr>
                <Th>API Key</Th>
                <Th isNumeric>Requests</Th>
                <Th isNumeric>Units consumed</Th>
                <Th isNumeric>Cost (₹)</Th>
                <Th>Last used</Th>
              </Tr>
            </Thead>
            <Tbody>
              {(data.api_key_breakdown || []).map((k) => (
                <Tr key={k.api_key_id}>
                  <Td fontFamily="mono" fontSize="xs">
                    {k.api_key_masked}
                  </Td>
                  <Td isNumeric>{formatIn(k.requests)}</Td>
                  <Td isNumeric>{formatIn(k.units_consumed)}</Td>
                  <Td isNumeric>{formatIn(k.total_cost)}</Td>
                  <Td fontSize="sm">{formatRelative(k.last_used)}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        </CardBody>
      </Card>
    </VStack>
  );
}
