// Profile page displaying user information with edit functionality
// Tabs are implemented as separate hooks + view components under components/profile/

import {
  Box,
  Card,
  Center,
  Heading,
  Spinner,
  Tabs,
  TabList,
  TabPanels,
  Tab,
  TabPanel,
  useColorModeValue,
  VStack,
  Text,
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useState, useEffect } from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import { useAuth } from "../hooks/useAuth";
import type { User } from "../types/auth";
import UserDetailsTab from "../components/profile/UserDetailsTab";
import ChangePasswordTab from "../components/profile/ChangePasswordTab";
import RolesTab from "../components/profile/RolesTab";
import { listTenants, listUsers } from "../services/tenantService";
import { resolveDefaultTenantId, tenantUsersToAuthUsers } from "../utils/defaultTenant";

const ProfilePage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();

  const [activeTabIndex, setActiveTabIndex] = useState(0);
  const [users, setUsers] = useState<User[]>([]);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const [defaultTenantId, setDefaultTenantId] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/auth?redirect=" + encodeURIComponent("/profile"));
    }
  }, [isAuthenticated, authLoading, router]);

  useEffect(() => {
    if (!isAuthenticated || authLoading || !user) return;
    const isPlatformAdmin = user?.roles?.includes("ADMIN");
    if (!isPlatformAdmin) return;

    let cancelled = false;
    setIsLoadingUsers(true);

    (async () => {
      try {
        const { tenants } = await listTenants();
        const tenantId = resolveDefaultTenantId(tenants);
        if (cancelled) return;
        setDefaultTenantId(tenantId);
        if (!tenantId) {
          setUsers([]);
          return;
        }
        const { users: tenantUsers } = await listUsers(tenantId);
        if (!cancelled) setUsers(tenantUsersToAuthUsers(tenantUsers));
      } catch (error) {
        console.error("Failed to fetch users for role assignment:", error);
        if (!cancelled) setUsers([]);
      } finally {
        if (!cancelled) setIsLoadingUsers(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, authLoading, user]);

  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");

  const isAdmin = Boolean(user?.roles?.includes("ADMIN"));
  const tabConfig = React.useMemo(() => {
    const tabs: { id: string; label: string; show: boolean }[] = [
      { id: "user-details", label: "User Details", show: true },
      { id: "change-password", label: "Change Password", show: true },
      { id: "roles", label: "Roles", show: isAdmin },
    ];
    return tabs.filter((t) => t.show);
  }, [isAdmin]);

  if (authLoading) {
    return (
      <ContentLayout>
        <Center h="400px">
          <Spinner size="xl" color="orange.500" />
        </Center>
      </ContentLayout>
    );
  }

  if (!isAuthenticated || !user) {
    return (
      <ContentLayout>
        <Center h="400px">
          <VStack spacing={4}>
            <Spinner size="xl" color="orange.500" />
            <Text color="gray.600">Redirecting to sign in...</Text>
          </VStack>
        </Center>
      </ContentLayout>
    );
  }

  return (
    <>
      <Head>
        <title>Profile - AI4I Platform</title>
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
          <Heading
            size="xl"
            mb={8}
            color="gray.800"
            userSelect="none"
            cursor="default"
            tabIndex={-1}
          >
            Profile
          </Heading>

          <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px">
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
                    {t.id === "change-password" && <ChangePasswordTab />}
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
          </Card>
        </Box>
      </ContentLayout>
    </>
  );
};

export default ProfilePage;
