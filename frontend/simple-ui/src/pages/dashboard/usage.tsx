import {
  Badge,
  Box,
  Card,
  CardBody,
  CardHeader,
  Center,
  Heading,
  HStack,
  Progress,
  SimpleGrid,
  Spinner,
  Stat,
  StatHelpText,
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
import Head from "next/head";
import React, { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/router";
import ContentLayout from "../../components/common/ContentLayout";
import TenantUsageDetailView from "../../components/dashboard/TenantUsageDetailView";
import { useAuth } from "../../hooks/useAuth";
import type { User } from "../../types/auth";
import {
  getAdopterUsage,
  getTenantUsage,
  topUpWallet,
  type AdopterUsageResponse,
  type TenantUsageDetailResponse,
} from "../../services/usageService";
import { getTenantIdFromToken } from "../../utils/helpers";
import { useToastWithDeduplication } from "../../hooks/useToastWithDeduplication";
import { extractErrorInfo } from "../../utils/errorHandler";
import {
  applyDemoAdopterUsage,
  applyDemoTenantUsage,
  DEMO_ACTIVE_SERVICES,
  USAGE_DEMO_ENABLED,
} from "../../utils/usageDemoMock";

function formatIn(n: number): string {
  return Number(n || 0).toLocaleString("en-IN");
}

function isTenantAdminUser(user: User | null): boolean {
  if (!user?.roles?.length) return false;
  return user.roles.some((r) => {
    const u = r.toUpperCase().replace(/\s+/g, "_");
    return (u.includes("TENANT") && u.includes("ADMIN")) || u === "TENANT_ADMIN" || u === "TENANT-ADMIN";
  });
}

function planBadgeStyle(plan: string): { bg: string; color: string } {
  const p = plan.toLowerCase();
  if (p.includes("premium") || p.includes("tier-1")) return { bg: "#1e3a5f", color: "white" };
  if (p.includes("standard") || p.includes("tier-2")) return { bg: "#dd6b20", color: "white" };
  if (p.includes("basic") || p.includes("tier-3")) return { bg: "gray.500", color: "white" };
  return { bg: "gray.400", color: "white" };
}

function tenantStatusBadge(status: string): { bg: string; color: string } {
  const u = status.toUpperCase();
  if (u === "BLOCKED") return { bg: "red.500", color: "white" };
  if (u === "NEAR LIMIT" || u === "NEAR_LIMIT") return { bg: "orange.400", color: "white" };
  if (u === "ACTIVE") return { bg: "green.500", color: "white" };
  return { bg: "green.500", color: "white" };
}

function serviceBarColorScheme(pct: number): string {
  if (pct > 80) return "orange";
  if (pct >= 50) return "yellow";
  return "blue";
}

export default function UsageDashboardPage() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const isAdopterAdmin = Boolean(user?.roles?.includes("ADMIN") || user?.is_superuser);
  const isTenantAdmin = isTenantAdminUser(user);
  const tenantIdFromToken = getTenantIdFromToken() || user?.tenant_id || "";
  const toast = useToastWithDeduplication();

  const [viewMode, setViewMode] = useState<"adopter" | "tenant">("adopter");
  const [loading, setLoading] = useState(true);
  const [adopterData, setAdopterData] = useState<AdopterUsageResponse | null>(null);
  const [tenantData, setTenantData] = useState<TenantUsageDetailResponse | null>(null);
  const [topup, setTopup] = useState("100");

  useEffect(() => {
    if (!isAdopterAdmin && isTenantAdmin && tenantIdFromToken) {
      setViewMode("tenant");
    }
    if (isAdopterAdmin && !isTenantAdmin) {
      setViewMode("adopter");
    }
  }, [isAdopterAdmin, isTenantAdmin, tenantIdFromToken]);

  const loadAdopter = useCallback(async () => {
    const raw = await getAdopterUsage();
    setAdopterData(USAGE_DEMO_ENABLED ? applyDemoAdopterUsage(raw) : raw);
  }, []);

  const loadTenantSelf = useCallback(async () => {
    if (!tenantIdFromToken) return;
    const raw = await getTenantUsage(tenantIdFromToken);
    setTenantData(USAGE_DEMO_ENABLED ? applyDemoTenantUsage(raw) : raw);
  }, [tenantIdFromToken]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (viewMode === "adopter" && isAdopterAdmin) {
        await loadAdopter();
      } else if (viewMode === "tenant" && tenantIdFromToken) {
        await loadTenantSelf();
      }
    } catch (e: unknown) {
      const { message } = extractErrorInfo(e);
      toast({ title: "Load failed", description: message, status: "error", isClosable: true });
    } finally {
      setLoading(false);
    }
  }, [viewMode, isAdopterAdmin, tenantIdFromToken, loadAdopter, loadTenantSelf, toast]);

  useEffect(() => {
    if (!authLoading && (!isAuthenticated || (!isAdopterAdmin && !isTenantAdmin))) {
      router.push("/");
    }
  }, [authLoading, isAuthenticated, isAdopterAdmin, isTenantAdmin, router]);

  useEffect(() => {
    if (!isAuthenticated || authLoading) return;
    if (!isAdopterAdmin && !isTenantAdmin) return;
    void load();
  }, [isAuthenticated, authLoading, isAdopterAdmin, isTenantAdmin, load]);

  const handleTopup = async () => {
    const amt = Number(topup);
    if (!tenantIdFromToken || Number.isNaN(amt) || amt <= 0) return;
    try {
      await topUpWallet(tenantIdFromToken, amt);
      toast({ title: "Top-up applied", status: "success", isClosable: true });
      await loadTenantSelf();
    } catch (e: unknown) {
      const { message } = extractErrorInfo(e);
      toast({ title: "Top-up failed", description: message, status: "error" });
    }
  };

  if (authLoading || !isAuthenticated) {
    return (
      <ContentLayout>
        <Center h="400px">
          <Spinner size="xl" color="orange.500" />
        </Center>
      </ContentLayout>
    );
  }

  if (!isAdopterAdmin && !isTenantAdmin) {
    return null;
  }

  const s = adopterData?.summary;

  return (
    <>
      <Head>
        <title>Usage Dashboard - AI4I Platform</title>
      </Head>
      <ContentLayout>
        <Box maxW="7xl" mx="auto" py={8} px={4}>
          <Box mb={8}>
            <Heading size="lg">Usage Dashboard</Heading>
          </Box>

          {loading ? (
            <Spinner />
          ) : viewMode === "tenant" && tenantData ? (
            <TenantUsageDetailView
              data={tenantData}
              showBack={false}
              showTopUp
              topUpValue={topup}
              onTopUpChange={setTopup}
              onTopUpSubmit={() => void handleTopup()}
            />
          ) : viewMode === "adopter" && isAdopterAdmin && adopterData && s ? (
            <VStack align="stretch" spacing={8}>
              <SimpleGrid columns={{ base: 1, sm: 2, md: 3, lg: 5 }} spacing={4}>
                <Card variant="outline">
                  <CardBody>
                    <Stat>
                      <StatLabel>Active tenants</StatLabel>
                      <StatNumber fontSize="3xl">{formatIn(s.active_tenants)}</StatNumber>
                      <StatHelpText color="gray.500">
                        {s.plan_breakdown.premium} premium, {s.plan_breakdown.standard} standard,{" "}
                        {s.plan_breakdown.basic} basic
                      </StatHelpText>
                    </Stat>
                  </CardBody>
                </Card>
                <Card variant="outline">
                  <CardBody>
                    <Stat>
                      <StatLabel>Active services</StatLabel>
                      <StatNumber fontSize="3xl">{formatIn(DEMO_ACTIVE_SERVICES)}</StatNumber>
                      <StatHelpText color="gray.500">Across the platform</StatHelpText>
                    </Stat>
                  </CardBody>
                </Card>
                <Card variant="outline">
                  <CardBody>
                    <Stat>
                      <StatLabel>Cost consumed (₹)</StatLabel>
                      <StatNumber fontSize="3xl">₹{formatIn(s.cost_consumed_this_month)}</StatNumber>
                      <StatHelpText color="gray.500">This month</StatHelpText>
                    </Stat>
                  </CardBody>
                </Card>
                <Card variant="outline">
                  <CardBody>
                    <Stat>
                      <StatLabel>Total requests today</StatLabel>
                      <StatNumber fontSize="3xl">{formatIn(s.total_requests_today)}</StatNumber>
                      <StatHelpText color={s.requests_vs_yesterday_percent >= 0 ? "green.500" : "red.500"}>
                        {s.requests_vs_yesterday_percent >= 0 ? "+" : ""}
                        {s.requests_vs_yesterday_percent}% vs yesterday
                      </StatHelpText>
                    </Stat>
                  </CardBody>
                </Card>
                <Card variant="outline">
                  <CardBody>
                    <Stat>
                      <StatLabel>Blocked requests</StatLabel>
                      <StatNumber fontSize="3xl">{formatIn(s.blocked_requests.total)}</StatNumber>
                      <StatHelpText color="gray.500">
                        Quota exceeded: {formatIn(s.blocked_requests.quota_exceeded)} | Rate limited:{" "}
                        {formatIn(s.blocked_requests.rate_limited)}
                      </StatHelpText>
                    </Stat>
                  </CardBody>
                </Card>
              </SimpleGrid>

              <SimpleGrid columns={{ base: 1, lg: 2 }} spacing={6} alignItems="flex-start">
                <Card variant="outline">
                  <CardHeader>
                    <Heading size="sm">Service usage — this month</Heading>
                  </CardHeader>
                  <CardBody pt={0}>
                    <VStack align="stretch" spacing={4}>
                      {(adopterData.service_usage || []).map((row) => {
                        const lim = row.limit > 0 ? row.limit : 1;
                        const pct = Math.min(100, (row.used / lim) * 100);
                        return (
                          <Box key={`${row.service_name}-${row.unit_type}`}>
                            <HStack justify="space-between" mb={1}>
                              <Text fontSize="sm" fontWeight="medium">
                                {row.service_name} ({row.unit_type})
                              </Text>
                              <Text fontSize="sm" color="gray.600">
                                {formatIn(row.used)} / {formatIn(row.limit)}
                              </Text>
                            </HStack>
                            <Progress
                              value={pct}
                              size="sm"
                              borderRadius="md"
                              colorScheme={serviceBarColorScheme(pct)}
                            />
                          </Box>
                        );
                      })}
                      {(!adopterData.service_usage || adopterData.service_usage.length === 0) && (
                        <Text fontSize="sm" color="gray.600">
                          No service usage this month.
                        </Text>
                      )}
                    </VStack>
                  </CardBody>
                </Card>

                <Card variant="outline">
                  <CardHeader>
                    <Heading size="sm">Top tenants by cost</Heading>
                  </CardHeader>
                  <CardBody pt={0}>
                    <Table size="sm" variant="simple">
                      <Thead>
                        <Tr>
                          <Th>Tenant</Th>
                          <Th>Plan</Th>
                          <Th isNumeric>Cost (₹)</Th>
                          <Th>Status</Th>
                        </Tr>
                      </Thead>
                      <Tbody>
                        {(adopterData.top_tenants || []).map((t) => (
                          <Tr
                            key={t.tenant_id}
                            _hover={{ bg: "gray.50", cursor: "pointer" }}
                            onClick={() =>
                              router.push(`/dashboard/usage/tenant/${encodeURIComponent(t.tenant_id)}`)
                            }
                          >
                            <Td>{t.tenant_name}</Td>
                            <Td>
                              <Badge {...planBadgeStyle(t.plan)} fontSize="0.65rem">
                                {t.plan || "—"}
                              </Badge>
                            </Td>
                            <Td isNumeric>{formatIn(t.cost)}</Td>
                            <Td>
                              <Badge {...tenantStatusBadge(t.status)} fontSize="0.65rem">
                                {t.status}
                              </Badge>
                            </Td>
                          </Tr>
                        ))}
                      </Tbody>
                    </Table>
                  </CardBody>
                </Card>
              </SimpleGrid>
            </VStack>
          ) : (
            <Text color="gray.600">No usage data.</Text>
          )}
        </Box>
      </ContentLayout>
    </>
  );
}
