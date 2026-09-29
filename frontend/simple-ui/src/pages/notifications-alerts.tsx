import { Center, Tab, TabList, TabPanel, TabPanels, Tabs } from "@chakra-ui/react";
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
import { INSTITUTION } from "../config/constants";
import { canAccessNotificationsAlerts, isPlatformAdminUser } from "../utils/rbac";

const NotificationsAlertsPage: React.FC = () => {
  const router = useRouter();
  const toast = useToastWithDeduplication();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();

  const canAccess = canAccessNotificationsAlerts(user?.roles);
  // A platform ADMIN who is also a Tenant Admin gets the catalog editor.
  const view = isPlatformAdminUser(user?.roles) ? "adopter" : "institution";

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
    if (!authLoading && isAuthenticated && !canAccess) {
      toast({
        title: "Access Denied",
        description: "You do not have permission to access Notifications & Alerts.",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      router.push("/");
    }
  }, [authLoading, isAuthenticated, canAccess, router, toast]);

  if (authLoading) {
    return (
      <ContentLayout>
        <Center h="400px">
          <LoadingSpinner size="xl" />
        </Center>
      </ContentLayout>
    );
  }

  if (!isAuthenticated || !canAccess) {
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
          description={
            view === "adopter"
              ? "Configure system-seeded notification and alert catalog for Adopter Admin"
              : `Choose which notifications and alerts your ${INSTITUTION.toLowerCase()} receives, and who else should get them`
          }
        />

        {view === "adopter" ? (
          // keepMounted: switching to Monitoring and back must not drop
          // unsaved catalog edits.
          <Tabs colorScheme="blue" isLazy lazyBehavior="keepMounted">
            <TabList mb={5}>
              <Tab fontWeight="semibold">Metering</Tab>
              <Tab fontWeight="semibold">Monitoring</Tab>
            </TabList>
            <TabPanels>
              <TabPanel px={0} py={0}>
                <NotificationAlertsManagement view="adopter" />
              </TabPanel>
              {/* Monitoring notifications & alerts aren't built yet — the tab
                  is a placeholder so the navigation is in place. */}
              <TabPanel px={0} py={0} />
            </TabPanels>
          </Tabs>
        ) : (
          <NotificationAlertsManagement view="institution" />
        )}
      </ContentLayout>
    </>
  );
};

export default NotificationsAlertsPage;
