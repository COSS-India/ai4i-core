import { Center } from "@chakra-ui/react";
import Head from "next/head";
import { useRouter } from "next/router";
import React, { useEffect } from "react";
import { useToastWithDeduplication } from "../utils/toast";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import LoadingSpinner from "../components/common/LoadingSpinner";
import NotificationAlertsManagement from "../components/notification-alerts/NotificationAlertsManagement";
import { useAuth } from "../hooks/useAuth";
import { getPlatformName } from "../config/runtimeConfig";
import { isPlatformAdminUser } from "../utils/rbac";

const NotificationsAlertsPage: React.FC = () => {
  const router = useRouter();
  const toast = useToastWithDeduplication();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();

  const isAdmin = isPlatformAdminUser(user?.roles);

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
          <LoadingSpinner size="xl" />
        </Center>
      </ContentLayout>
    );
  }

  if (!isAuthenticated || !isAdmin) {
    return (
      <ContentLayout>
        <Center h="400px">
          <LoadingSpinner size="xl" label="Redirecting..." />
        </Center>
      </ContentLayout>
    );
  }

  return (
    <>
      <Head>
        <title>{`Platform Settings - ${getPlatformName()}`}</title>
        <meta
          name="description"
          content="Configure system-seeded notifications and threshold alerts"
        />
      </Head>

      <ContentLayout>
        <ManagementPageHeader
          title="Platform Settings"
          description="Configure system-seeded notification and alert catalog for Adopter Admin"
        />

        <NotificationAlertsManagement />
      </ContentLayout>
    </>
  );
};

export default NotificationsAlertsPage;
