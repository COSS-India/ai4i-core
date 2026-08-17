import {
  Box,
  Center,
  Spinner,
  VStack,
  Text,
} from "@chakra-ui/react";
import Head from "next/head";
import React from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import { useAuth } from "../hooks/useAuth";
import AlertingTab from "../components/profile/AlertingTab";

/**
 * Alerts Management temporarily removed from UI.
 * To restore: set ALERTS_MANAGEMENT_UI_ENABLED = true, and uncomment related
 * Sidebar / AuthGuard / _app / Header entries.
 */
const ALERTS_MANAGEMENT_UI_ENABLED = false;

const AlertsManagementPage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();

  const isAdmin = Boolean(user?.roles?.includes("ADMIN"));

  React.useEffect(() => {
    if (!ALERTS_MANAGEMENT_UI_ENABLED) {
      router.replace("/");
      return;
    }
    if (!authLoading && (!isAuthenticated || !isAdmin)) {
      router.push("/");
    }
  }, [isAuthenticated, authLoading, isAdmin, router]);

  if (!ALERTS_MANAGEMENT_UI_ENABLED) {
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

  if (authLoading) {
    return (
      <ContentLayout>
        <Center h="400px">
          <Spinner size="xl" color="orange.500" />
        </Center>
      </ContentLayout>
    );
  }

  if (!isAuthenticated || !isAdmin) {
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
        <title>Alerts Management - AI4I Platform</title>
        <meta name="description" content="Manage alert definitions, notification receivers, and routing rules" />
      </Head>

      <ContentLayout>
        <Box maxW="7xl" mx="auto" py={8} px={4}>
          <ManagementPageHeader
            title="Alerts Management"
            description="Define alert policies and configure notification routing"
          />

          <AlertingTab isActive={true} />
        </Box>
      </ContentLayout>
    </>
  );
};

export default AlertsManagementPage;
