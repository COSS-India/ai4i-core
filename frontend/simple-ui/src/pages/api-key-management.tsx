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
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import { useAuth } from "../hooks/useAuth";
import authService from "../services/authService";
import CreateApiKeyTab from "../components/profile/CreateApiKeyTab";
import ApiKeyManagementTab from "../components/profile/ApiKeyManagementTab";
import { useApiKey } from "../hooks/useApiKey";
import type { User } from "../types/auth";
import type { APIKeyResponse } from "../types/auth";

const ApiKeyManagementPage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const { setApiKey } = useApiKey();

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

  const isAdmin = Boolean(user?.roles?.includes("ADMIN") || user?.is_superuser);
  const isTenantAdmin = Boolean(user?.roles?.includes("TENANT ADMIN"));

  const showApiKeyManagement = isAdmin || isTenantAdmin;

  useEffect(() => {
    if (!authLoading && (!isAuthenticated || !showApiKeyManagement)) {
      router.push("/profile");
    }
  }, [authLoading, isAuthenticated, router, showApiKeyManagement]);

  // Persist selected API key ID to localStorage
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (selectedApiKeyId !== null) {
      localStorage.setItem("selected_api_key_id", selectedApiKeyId.toString());
    } else {
      localStorage.removeItem("selected_api_key_id");
    }
  }, [selectedApiKeyId]);

  // Restore API key value when selection or list changes
  useEffect(() => {
    if (selectedApiKeyId === null) return;
    if (apiKeys.length === 0) return;
    const selectedKey = apiKeys.find((key) => key.id === selectedApiKeyId);
    if (selectedKey?.key_value) {
      setApiKey(selectedKey.key_value);
    }
  }, [apiKeys, selectedApiKeyId, setApiKey]);

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

  // Fetch users for create/manage tabs (admin + tenant admin)
  useEffect(() => {
    if (!isAuthenticated || authLoading || !user) return;
    if (!showApiKeyManagement) return;

    setIsLoadingUsers(true);
    authService
      .getAllUsers()
      .then((usersList) => setUsers(usersList))
      .catch((error) => {
        console.error("Failed to fetch users:", error);
      })
      .finally(() => setIsLoadingUsers(false));
  }, [authLoading, isAuthenticated, showApiKeyManagement, user]);

  useEffect(() => {
    if (!authLoading && isAuthenticated) {
      handleFetchApiKeys();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, isAuthenticated]);

  const tabs = useMemo(() => {
    const t: { id: "create" | "manage"; label: string; show: boolean }[] = [
      { id: "create", label: "Create API Key", show: isAdmin || isTenantAdmin },
      { id: "manage", label: "Manage API Keys", show: isAdmin },
    ];
    return t.filter((x) => x.show);
  }, [isAdmin, isTenantAdmin]);

  const manageTabIndex = tabs.findIndex((t) => t.id === "manage");

  const cardBg = useColorModeValue("white", "gray.800");
  const cardBorder = useColorModeValue("gray.200", "gray.700");

  if (authLoading) {
    return (
      <ContentLayout>
        <Center h="400px">
          <Spinner size="xl" color="orange.500" />
        </Center>
      </ContentLayout>
    );
  }

  if (!isAuthenticated || !user || !showApiKeyManagement) {
    return (
      <ContentLayout>
        <Center h="400px">
          <VStack spacing={4}>
            <Spinner size="xl" color="orange.500" />
            <Heading size="sm" color="gray.600">
              Redirecting...
            </Heading>
          </VStack>
        </Center>
      </ContentLayout>
    );
  }

  return (
    <>
      <Head>
        <title>API Key Management - AI4I Platform</title>
        <meta name="description" content="Create and manage API keys" />
      </Head>

      <ContentLayout>
        <Box maxW="7xl" mx="auto" py={8} px={4}>
          <Heading size="xl" mb={8} color="gray.800" userSelect="none">
            API Key Management
          </Heading>

          <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px">
            <Tabs
              colorScheme="blue"
              variant="enclosed"
              index={activeTabIndex}
              onChange={(idx) => setActiveTabIndex(idx)}
            >
              <TabList>
                {tabs.map((t) => (
                  <Tab key={t.id} fontWeight="semibold">
                    {t.label}
                  </Tab>
                ))}
              </TabList>

              <TabPanels>
                {tabs.map((t) => (
                  <TabPanel key={t.id} px={0} pt={6}>
                    {t.id === "create" && (
                      <CreateApiKeyTab
                        users={users}
                        isLoadingUsers={isLoadingUsers}
                        setApiKeys={setApiKeys}
                        setSelectedApiKeyId={setSelectedApiKeyId}
                      />
                    )}
                    {t.id === "manage" && (
                      <ApiKeyManagementTab
                        users={users}
                        isLoadingUsers={false}
                        isActive={activeTabIndex === manageTabIndex}
                      />
                    )}
                  </TabPanel>
                ))}
              </TabPanels>
            </Tabs>
          </Card>

          {/* Hidden fetch activity indicators are intentionally not shown to avoid UX changes */}
          {(isFetchingApiKey || isLoadingApiKeys) && null}
        </Box>
      </ContentLayout>
    </>
  );
};

export default ApiKeyManagementPage;

