import {
  Box,
  Center,
  Heading,
  Spinner,
  useDisclosure,
  VStack,
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useEffect, useRef, useState } from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import CreateButton from "../components/common/CreateButton";
import FormActions from "../components/common/FormActions";
import FormPage from "../components/common/FormPage";
import FormSection from "../components/common/FormSection";
import { useAuth } from "../hooks/useAuth";
import CreateApiKeyTab from "../components/profile/CreateApiKeyTab";
import ApiKeyManagementTab from "../components/profile/ApiKeyManagementTab";
import { userMayManageApiKeys } from "../utils/rbac";
import { getPlatformName } from "../config/runtimeConfig";

const ApiKeyManagementPage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const { isOpen: isCreateOpen, onOpen: onCreateOpen, onClose: closeCreate } =
    useDisclosure();
  const [isCreatingKey, setIsCreatingKey] = useState(false);
  const [hasCreatedToken, setHasCreatedToken] = useState(false);
  const isCreatingKeyRef = useRef(isCreatingKey);
  const hasCreatedTokenRef = useRef(hasCreatedToken);
  const allowRouteLeaveRef = useRef(false);
  isCreatingKeyRef.current = isCreatingKey;
  hasCreatedTokenRef.current = hasCreatedToken;

  const confirmDiscardApiKey = () => {
    const creating = isCreatingKeyRef.current;
    const hasToken = hasCreatedTokenRef.current;
    if (!creating && !hasToken) return true;
    if (allowRouteLeaveRef.current) return true;
    const ok = window.confirm(
      creating
        ? "This API key is still being created. Leaving now will not show its token. Leave anyway?"
        : "This API key token will not be shown again. Leave this page?",
    );
    if (ok) allowRouteLeaveRef.current = true;
    return ok;
  };

  const onCreateClose = () => {
    setHasCreatedToken(false);
    closeCreate();
  };

  useEffect(() => {
    if (!isCreatingKey && !hasCreatedToken) {
      allowRouteLeaveRef.current = false;
    }
  }, [isCreatingKey, hasCreatedToken]);

  useEffect(() => {
    const onRouteChangeStart = () => {
      if (!isCreatingKeyRef.current && !hasCreatedTokenRef.current) return;
      if (confirmDiscardApiKey()) return;
      router.events.emit("routeChangeError");
      throw "Route change aborted.";
    };
    router.events.on("routeChangeStart", onRouteChangeStart);
    return () => {
      router.events.off("routeChangeStart", onRouteChangeStart);
    };
  }, [router.events]);
  const refreshManagedKeysRef = useRef<(() => Promise<void>) | null>(null);
  const showList = !isCreateOpen;

  const showApiKeyManagement = userMayManageApiKeys(user?.roles);

  useEffect(() => {
    if (!authLoading && (!isAuthenticated || !showApiKeyManagement)) {
      router.push("/profile");
    }
  }, [authLoading, isAuthenticated, router, showApiKeyManagement]);

  if (authLoading) {
    return (
      <ContentLayout>
        <Center h="400px">
          <Spinner size="xl" />
        </Center>
      </ContentLayout>
    );
  }

  if (!isAuthenticated || !user || !showApiKeyManagement) {
    return (
      <ContentLayout>
        <Center h="400px">
          <VStack spacing={4}>
            <Spinner size="xl" />
            <Heading size="sm" color="ink.600">
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
        <title>{`API Key Management - ${getPlatformName()}`}</title>
        <meta name="description" content="Create and manage API keys" />
      </Head>

      <ContentLayout>
        {isCreateOpen ? (
          <FormPage
            title="Create API Key"
            description="Create a key, set permissions, and allocate a required budget as a percentage of the application."
            parent={{
              label: "API Key Management",
              href: "/api-key-management",
              onNavigate: (event) => {
                if (!confirmDiscardApiKey()) {
                  event.preventDefault();
                  return;
                }
                onCreateClose();
              },
            }}
            onLeave={() => {
              if (!confirmDiscardApiKey()) return;
              onCreateClose();
            }}
            footer={({ leave }) => (
              <FormActions
                cancelLabel="Cancel"
                submitLabel="Create API Key"
                onCancel={leave}
                submitType="submit"
                form="create-api-key-form"
                isLoading={isCreatingKey}
                loadingText="Creating..."
                justify="space-between"
                pt={0}
              />
            )}
          >
            <FormSection title="API Key">
              <CreateApiKeyTab
                tenantId={user.tenant_id}
                onApiKeyCreated={() => void refreshManagedKeysRef.current?.()}
                hideActions
                formId="create-api-key-form"
                onCreatingChange={setIsCreatingKey}
                onCreatedTokenChange={setHasCreatedToken}
              />
            </FormSection>
          </FormPage>
        ) : null}
        <Box hidden={!showList}>
          <ManagementPageHeader
            title="API Key Management"
            description="Create keys, set permissions, and allocate a required budget as a percentage of the application"
            actions={
              <CreateButton onClick={onCreateOpen}>Create API Key</CreateButton>
            }
          />
          <ApiKeyManagementTab
            isActive
            onRegisterRefresh={(refresh) => {
              refreshManagedKeysRef.current = refresh;
            }}
          />
        </Box>
      </ContentLayout>
    </>
  );
};

export default ApiKeyManagementPage;
