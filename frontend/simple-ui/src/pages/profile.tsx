// Profile page displaying user information and API key with edit functionality
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
import { useApiKey } from "../hooks/useApiKey";
import authService from "../services/authService";
import type { User } from "../types/auth";
import type { APIKeyResponse } from "../types/auth";
import UserDetailsTab from "../components/profile/UserDetailsTab";
import ApiKeyTab from "../components/profile/ApiKeyTab";
import RolesTab from "../components/profile/RolesTab";
import CreateApiKeyTab from "../components/profile/CreateApiKeyTab";
import ApiKeyManagementTab from "../components/profile/ApiKeyManagementTab";
import TenantManagementTab from "../components/profile/TenantManagementTab";

const ProfilePage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const { setApiKey } = useApiKey();

  // State owned by profile: tab index, API keys list (shared by API Key tab and Create API Key tab), users (shared by Roles, Create API Key, API Key Management)
  const [activeTabIndex, setActiveTabIndex] = useState(0);
  const [apiKeys, setApiKeys] = useState<APIKeyResponse[]>([]);
  const [selectedApiKeyId, setSelectedApiKeyId] = useState<number | null>(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("selected_api_key_id");
      return stored ? parseInt(stored, 10) : null;
    }
    return null;
  });
  const [users, setUsers] = useState<User[]>([]);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const [isFetchingApiKey, setIsFetchingApiKey] = useState(false);
  const [isLoadingApiKeys, setIsLoadingApiKeys] = useState(false);

  // Persist selected API key ID to localStorage
  useEffect(() => {
    if (typeof window !== "undefined") {
      if (selectedApiKeyId !== null) {
        localStorage.setItem("selected_api_key_id", selectedApiKeyId.toString());
      } else {
        localStorage.removeItem("selected_api_key_id");
      }
    }
  }, [selectedApiKeyId]);

  // Restore API key value when selection or list changes
  useEffect(() => {
    if (selectedApiKeyId !== null && apiKeys.length > 0) {
      const selectedKey = apiKeys.find((key) => key.id === selectedApiKeyId);
      if (selectedKey?.key_value) {
        setApiKey(selectedKey.key_value);
      }
    }
  }, [selectedApiKeyId, apiKeys, setApiKey]);

  // Redirect if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      if (typeof window !== "undefined") {
        sessionStorage.setItem("redirectAfterAuth", "/profile");
      }
      router.push("/auth");
    }
  }, [isAuthenticated, authLoading, router]);

  // Fetch all users (Admin only)
  useEffect(() => {
    if (!isAuthenticated || authLoading || !user) return;
    const isAdmin = user?.roles?.includes("ADMIN") || user?.is_superuser;
    if (!isAdmin) return;

    setIsLoadingUsers(true);
    authService
      .getAllUsers()
      .then((usersList) => setUsers(usersList))
      .catch((error) => {
        console.error("Failed to fetch users:", error);
      })
      .finally(() => setIsLoadingUsers(false));
  }, [isAuthenticated, authLoading, user]);

  const handleFetchApiKeys = async () => {
    setIsFetchingApiKey(true);
    setIsLoadingApiKeys(true);
    try {
      const response = await authService.listApiKeys();
      const keys = Array.isArray(response.api_keys) ? response.api_keys : [];
      setApiKeys(keys);
      setSelectedApiKeyId(response.selected_api_key_id ?? null);
    } catch (error) {
      console.error("Failed to fetch API keys:", error);
    } finally {
      setIsFetchingApiKey(false);
      setIsLoadingApiKeys(false);
    }
  };

  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");

  const isAdmin = Boolean(user?.roles?.includes("ADMIN") || user?.is_superuser);
  const isModerator = Boolean(user?.roles?.includes("MODERATOR"));
  const showMultiTenant = Boolean( user?.is_superuser || user?.is_tenant);
  // Single source of truth: tab order must match TabPanels 1:1
  const tabConfig = React.useMemo(() => {
    const tabs: { id: string; label: string; show: boolean }[] = [
      { id: "user-details", label: "User Details", show: true },
      { id: "api-key", label: "API Key", show: true },
      { id: "roles", label: "Roles", show: isAdmin },
      { id: "create-api-key", label: "Create API Key", show: isAdmin },
      { id: "api-key-management", label: "API Key Management", show: isAdmin },
      { id: "multi-tenant", label: "Multi Tenant Management", show: showMultiTenant },
    ];
    return tabs.filter((t) => t.show);
  }, [isAdmin, isModerator, showMultiTenant]);

  const apiKeyTabIndex = 1;
  const permissionsTabIndex = isAdmin ? 3 : -1;
  const apiKeyManagementTabIndex = tabConfig.findIndex((t) => t.id === "api-key-management");
  const multiTenantTabIndex = tabConfig.findIndex((t) => t.id === "multi-tenant");

  const handleTabChange = (index: number) => {
    setActiveTabIndex(index);
    if (index === apiKeyTabIndex) {
      handleFetchApiKeys();
    }
    if (index === permissionsTabIndex && apiKeys.length === 0) {
      handleFetchApiKeys();
    }
  };

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
        <meta name="description" content="User profile and API key management" />
      </Head>

      <ContentLayout>
        <Box
          maxW={
            user?.roles?.includes("ADMIN") || user?.roles?.includes("MODERATOR") || user?.is_superuser
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
              onChange={handleTabChange}
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
                    {t.id === "api-key" && (
                      <ApiKeyTab
                        apiKeys={apiKeys}
                        selectedApiKeyId={selectedApiKeyId}
                        setSelectedApiKeyId={setSelectedApiKeyId}
                        isFetchingApiKey={isFetchingApiKey}
                        isLoadingApiKeys={isLoadingApiKeys}
                        onFetchApiKeys={handleFetchApiKeys}
                      />
                    )}
                    {t.id === "roles" && <RolesTab users={users} isLoadingUsers={isLoadingUsers} />}
                    {t.id === "create-api-key" && (
                      <CreateApiKeyTab
                        users={users}
                        isLoadingUsers={isLoadingUsers}
                        setApiKeys={setApiKeys}
                        setSelectedApiKeyId={setSelectedApiKeyId}
                      />
                    )}
                    {t.id === "api-key-management" && (
                      <ApiKeyManagementTab
                        users={users}
                        isActive={activeTabIndex === apiKeyManagementTabIndex}
                      />
                    )}
                    {t.id === "multi-tenant" && (
                      <TenantManagementTab isActive={activeTabIndex === multiTenantTabIndex} />
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
