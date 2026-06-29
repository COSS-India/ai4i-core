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
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import { useAuth } from "../hooks/useAuth";
import { isPlatformAdminUser, isTenantAdminUser } from "../utils/rbac";
import CreateApiKeyTab from "../components/profile/CreateApiKeyTab";
import ApiKeyManagementTab from "../components/profile/ApiKeyManagementTab";
const ApiKeyManagementPage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();

  const [activeTabIndex, setActiveTabIndex] = useState(0);
  const refreshManagedKeysRef = useRef<(() => Promise<void>) | null>(null);

  const isAdmin = isPlatformAdminUser(user?.roles);
  const isTenantAdmin = isTenantAdminUser(user?.roles);

  const showApiKeyManagement = isAdmin || isTenantAdmin;

  useEffect(() => {
    if (!authLoading && (!isAuthenticated || !showApiKeyManagement)) {
      router.push("/profile");
    }
  }, [authLoading, isAuthenticated, router, showApiKeyManagement]);

  const tabs = useMemo(() => {
    const t: { id: "create" | "manage"; label: string; show: boolean }[] = [
      { id: "create", label: "Create API Key", show: isAdmin || isTenantAdmin },
      { id: "manage", label: "Manage API Keys", show: isAdmin || isTenantAdmin },
    ];
    return t.filter((x) => x.show);
  }, [isAdmin, isTenantAdmin]);

  const manageTabIndex = tabs.findIndex((t) => t.id === "manage");

  const handleTabChange = (idx: number) => {
    setActiveTabIndex(idx);
    if (tabs[idx]?.id === "manage") {
      void refreshManagedKeysRef.current?.();
    }
  };

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
        <title>Manage API - AI4I Platform</title>
        <meta name="description" content="Create and manage API keys" />
      </Head>

      <ContentLayout>
        <Box maxW="7xl" mx="auto" py={8} px={4}>
          <ManagementPageHeader
            title="Manage API"
            description="Create and manage API keys for your account"
          />

          <Card bg={cardBg} borderColor={cardBorder} borderWidth="1px">
            <Tabs
              colorScheme="blue"
              variant="enclosed"
              isLazy={false}
              index={activeTabIndex}
              onChange={handleTabChange}
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
                        onApiKeyCreated={() => void refreshManagedKeysRef.current?.()}
                      />
                    )}
                    {t.id === "manage" && (
                      <ApiKeyManagementTab
                        isActive={activeTabIndex === manageTabIndex}
                        onRegisterRefresh={(refresh) => {
                          refreshManagedKeysRef.current = refresh;
                        }}
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

export default ApiKeyManagementPage;
