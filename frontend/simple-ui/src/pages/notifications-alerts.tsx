import { Box, Center, Spinner, Text, VStack } from "@chakra-ui/react";
import Head from "next/head";
import { useRouter } from "next/router";
import React, { useEffect } from "react";
import { useToastWithDeduplication } from "../utils/toast";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import NotificationAlertsManagement from "../components/notification-alerts/NotificationAlertsManagement";
import { useAuth } from "../hooks/useAuth";
import { useAdminTableSurface } from "../components/common/table";
import { getPlatformName } from "../config/runtimeConfig";

const NotificationsAlertsPage: React.FC = () => {
  const router = useRouter();
  const toast = useToastWithDeduplication();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const { cardBg, borderColor } = useAdminTableSurface();

  const isAdmin = Boolean(user?.roles?.includes("ADMIN"));

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      toast({
        title: "Authentication Required",
        description: "Please log in to access Notifications & Alerts.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      router.push("/auth");
    }
  }, [authLoading, isAuthenticated, router, toast]);

  useEffect(() => {
    if (!authLoading && isAuthenticated && !isAdmin) {
      toast({
        title: "Access Denied",
        description: "You do not have permission to access Notifications & Alerts.",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      router.push("/");
    }
  }, [authLoading, isAuthenticated, isAdmin, router, toast]);

  if (authLoading) {
    return (
      <ContentLayout>
        <Center h="400px">
          <Spinner size="xl" color="blue.500" />
        </Center>
      </ContentLayout>
    );
  }

  if (!isAuthenticated || !isAdmin) {
    return (
      <ContentLayout>
        <Center h="400px">
          <VStack spacing={4}>
            <Spinner size="xl" color="blue.500" />
            <Text color="gray.600">Redirecting...</Text>
          </VStack>
        </Center>
      </ContentLayout>
    );
  }

  return (
    <>
      <Head>
        <title>{`Notifications & Alerts - ${getPlatformName()}`}</title>
        <meta
          name="description"
          content="Configure system-seeded notifications and threshold alerts"
        />
      </Head>

      <ContentLayout>
        <Box maxW="full" mx="auto" py={8} px={6}>
          <ManagementPageHeader
            title="Notifications & Alerts"
            description="Configure system-seeded notification and alert catalog for Adopter Admin"
          />

          <Box
            mt={6}
            bg={cardBg}
            borderWidth="1px"
            borderColor={borderColor}
            borderRadius="lg"
            p={6}
          >
            <NotificationAlertsManagement />
          </Box>
        </Box>
      </ContentLayout>
    </>
  );
};

export default NotificationsAlertsPage;
