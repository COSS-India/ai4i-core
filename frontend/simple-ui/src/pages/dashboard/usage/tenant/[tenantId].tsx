import { Box, Center, Spinner, Text } from "@chakra-ui/react";
import Head from "next/head";
import { useRouter } from "next/router";
import React, { useCallback, useEffect, useState } from "react";
import ContentLayout from "../../../../components/common/ContentLayout";
import TenantUsageDetailView from "../../../../components/dashboard/TenantUsageDetailView";
import { useAuth } from "../../../../hooks/useAuth";
import { getTenantUsage, type TenantUsageDetailResponse } from "../../../../services/usageService";
import { useToastWithDeduplication } from "../../../../hooks/useToastWithDeduplication";
import { extractErrorInfo } from "../../../../utils/errorHandler";
import { getTenantIdFromToken } from "../../../../utils/helpers";
import { applyDemoTenantUsage, USAGE_DEMO_ENABLED } from "../../../../utils/usageDemoMock";

function isTenantAdminUser(user: import("../../../../types/auth").User | null): boolean {
  if (!user?.roles?.length) return false;
  return user.roles.some((r) => {
    const u = r.toUpperCase().replace(/\s+/g, "_");
    return (u.includes("TENANT") && u.includes("ADMIN")) || u === "TENANT_ADMIN" || u === "TENANT-ADMIN";
  });
}

export default function TenantUsageDrilldownPage() {
  const router = useRouter();
  const raw = router.query.tenantId;
  const tenantId = typeof raw === "string" ? raw : "";
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const isAdopterAdmin = Boolean(user?.roles?.includes("ADMIN") || user?.is_superuser);
  const isTenantAdmin = isTenantAdminUser(user);
  const toast = useToastWithDeduplication();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<TenantUsageDetailResponse | null>(null);

  const load = useCallback(async () => {
    if (!tenantId) return;
    setLoading(true);
    try {
      const raw = await getTenantUsage(tenantId);
      setData(USAGE_DEMO_ENABLED ? applyDemoTenantUsage(raw) : raw);
    } catch (e: unknown) {
      const { message } = extractErrorInfo(e);
      toast({ title: "Load failed", description: message, status: "error", isClosable: true });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [tenantId, toast]);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/");
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (!isAuthenticated || authLoading) return;
    if (!isAdopterAdmin && !isTenantAdmin) {
      router.push("/");
      return;
    }
    if (!tenantId) return;
    const tokenTid = getTenantIdFromToken() || user?.tenant_id || "";
    if (isTenantAdmin && !isAdopterAdmin && String(tokenTid) !== tenantId) {
      router.replace("/dashboard/usage");
      return;
    }
    void load();
  }, [isAuthenticated, authLoading, isAdopterAdmin, isTenantAdmin, tenantId, load, router, user?.tenant_id]);

  if (authLoading || !isAuthenticated) {
    return (
      <ContentLayout>
        <Center h="400px">
          <Spinner size="xl" color="orange.500" />
        </Center>
      </ContentLayout>
    );
  }

  return (
    <>
      <Head>
        <title>Tenant usage - AI4I Platform</title>
      </Head>
      <ContentLayout>
        <Box maxW="7xl" mx="auto" py={8} px={4}>
          {loading ? (
            <Spinner />
          ) : data ? (
            <TenantUsageDetailView
              data={data}
              showBack
              onBack={() => router.push("/dashboard/usage")}
            />
          ) : (
            <Text color="gray.600">Unable to load tenant.</Text>
          )}
        </Box>
      </ContentLayout>
    </>
  );
}
