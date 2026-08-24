import {
  Box,
  Center,
  Spinner,
  Text,
  VStack,
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useEffect, useMemo } from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import UsageDashboard from "../components/metering/UsageDashboard";
import { useAuth } from "../hooks/useAuth";
import { showToast } from "../utils/toast";
import { INSTITUTION } from "../config/constants";
import { getTenantIdFromToken } from "../utils/helpers";
import {
  canAccessUsageDashboard,
} from "../utils/rbac";
import { getPlatformName } from "../config/runtimeConfig";

const UsageDashboardPage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();

  const canAccess = canAccessUsageDashboard(user?.roles);

  const tenantId = useMemo(
    () => user?.tenant_id?.trim() || getTenantIdFromToken() || null,
    [user?.tenant_id],
  );

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      showToast({
        type: "warning",
        message: "Please log in to view the usage dashboard.",
      });
      router.push("/auth");
    }
  }, [authLoading, isAuthenticated, router]);

  useEffect(() => {
    if (!authLoading && isAuthenticated && !canAccess) {
      showToast({
        type: "error",
        message: "You do not have permission to view the usage dashboard.",
      });
      router.push("/");
    }
  }, [authLoading, isAuthenticated, canAccess, router]);

  if (authLoading) {
    return (
      <ContentLayout>
        <Center h="400px">
          <Spinner size="xl" color="orange.500" />
        </Center>
      </ContentLayout>
    );
  }

  if (!isAuthenticated || !canAccess) {
    return (
      <ContentLayout>
        <Center h="400px">
          <VStack spacing={4}>
            <Spinner size="xl" color="orange.500" />
            <Text color="gray.600">Redirecting...</Text>
          </VStack>
        </Center>
      </ContentLayout>
    );
  }

  return (
    <>
      <Head>
        <title>{`Usage Dashboard - ${getPlatformName()}`}</title>
        <meta
          name="description"
          content={`Monitor service consumption, model consumption, ${INSTITUTION.toLowerCase()} activity, and platform throughput`}
        />
      </Head>

      <ContentLayout>
        <Box maxW="7xl" mx="auto" py={4} px={2}>
          <UsageDashboard
            userRoles={user?.roles}
            tenantId={tenantId}
          />
        </Box>
      </ContentLayout>
    </>
  );
};

export default UsageDashboardPage;
