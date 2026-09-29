// Profile page displaying user information with edit functionality
// Tabs are implemented as separate hooks + view components under components/profile/

import {
  Box,
  Center,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import LoadingSpinner from "../components/common/LoadingSpinner";
import { useAuth } from "../hooks/useAuth";
import { useTenantsList } from "../hooks/useTenantsList";
import UserDetailsTab from "../components/profile/UserDetailsTab";
import ChangePasswordTab from "../components/profile/ChangePasswordTab";
import RolesTab from "../components/profile/RolesTab";
import { listUsers } from "../services/tenantService";
import { resolveDefaultTenantId, tenantUsersToAuthUsers } from "../utils/defaultTenant";
import { canChangeOwnPassword, isPlatformAdminUser } from "../utils/rbac";
import { getPlatformName } from "../config/runtimeConfig";

const ProfilePage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();

  const [activeTabIndex, setActiveTabIndex] = useState(0);
  const isAdmin = isPlatformAdminUser(user?.roles);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/auth?redirect=" + encodeURIComponent("/profile"));
    }
  }, [isAuthenticated, authLoading, router]);

  const tenantsQuery = useTenantsList({
    enabled: isAuthenticated && !authLoading && isAdmin,
  });
  const defaultTenantId = useMemo(
    () => resolveDefaultTenantId(tenantsQuery.data?.tenants ?? []),
    [tenantsQuery.data?.tenants],
  );
  const usersQuery = useQuery({
    queryKey: ["profile-tenant-users", defaultTenantId],
    queryFn: async () => {
      const { users: tenantUsers } = await listUsers(defaultTenantId!);
      return tenantUsersToAuthUsers(tenantUsers);
    },
    enabled: Boolean(defaultTenantId),
    staleTime: 5 * 60 * 1000,
  });
  const users = usersQuery.data ?? [];
  const isLoadingUsers = tenantsQuery.isLoading || usersQuery.isLoading;

  const showChangePassword = canChangeOwnPassword(user?.roles);
  const tabConfig = React.useMemo(() => {
    const tabs: { id: string; label: string; show: boolean }[] = [
      { id: "user-details", label: "User Details", show: true },
      { id: "change-password", label: "Change Password", show: showChangePassword },
      { id: "roles", label: "Roles", show: isAdmin },
    ];
    return tabs.filter((t) => t.show);
  }, [isAdmin, showChangePassword]);

  if (authLoading) {
    return (
      <ContentLayout>
        <Center h="400px">
          <LoadingSpinner size="xl" />
        </Center>
      </ContentLayout>
    );
  }

  if (!isAuthenticated || !user) {
    return (
      <ContentLayout>
        <Center h="400px">
          <LoadingSpinner size="xl" label="Redirecting to sign in..." />
        </Center>
      </ContentLayout>
    );
  }

  return (
    <>
      <Head>
        <title>{`Profile - ${getPlatformName()}`}</title>
        <meta name="description" content="User profile" />
      </Head>

      <ContentLayout>
        <Box
          maxW={
            user?.roles?.includes("ADMIN") || user?.roles?.includes("MODERATOR")
              ? "7xl"
              : "4xl"
          }
          mx="auto"
          py={8}
          px={4}
        >
          <ManagementPageHeader
            title="Profile"
            description="Your account details, password, and role settings"
          />

          <Tabs
            colorScheme="blue"
            variant="enclosed"
            index={activeTabIndex}
            onChange={setActiveTabIndex}
          >
            <TabList>
              {tabConfig.map((t) => (
                <Tab key={t.id} fontWeight="semibold">
                  {t.label}
                </Tab>
              ))}
            </TabList>

            <TabPanels>
              {tabConfig.map((t) => (
                <TabPanel key={t.id} px={0} pt={6}>
                  {t.id === "user-details" && <UserDetailsTab />}
                  {t.id === "change-password" && (
                    <ChangePasswordTab
                      onCancel={() =>
                        setActiveTabIndex(
                          tabConfig.findIndex((tab) => tab.id === "user-details")
                        )
                      }
                    />
                  )}
                  {t.id === "roles" && (
                    <RolesTab
                      users={users}
                      isLoadingUsers={isLoadingUsers}
                      defaultTenantId={defaultTenantId}
                    />
                  )}
                </TabPanel>
              ))}
            </TabPanels>
          </Tabs>
        </Box>
      </ContentLayout>
    </>
  );
};

export default ProfilePage;
