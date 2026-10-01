import {
  Button,
  Center,
  Heading,
  HStack,
  Spinner,
  useDisclosure,
  VStack,
} from "@chakra-ui/react";
import { FiRefreshCw, FiSliders } from "react-icons/fi";
import Head from "next/head";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import CreateButton from "../components/common/CreateButton";
import FormActions from "../components/common/FormActions";
import FormDrawer from "../components/common/FormDrawer";
import { useAuth } from "../hooks/useAuth";
import { BUDGET_COPY } from "../config/budgetMessages";
import CreateApiKeyTab from "../components/profile/CreateApiKeyTab";
import ApiKeyManagementTab, {
  type ApiKeyPageActions,
} from "../components/profile/ApiKeyManagementTab";
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

  const requestCloseCreate = () => {
    if (!confirmDiscardApiKey()) return;
    onCreateClose();
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
  const [pageActions, setPageActions] = useState<ApiKeyPageActions | null>(null);
  const bindPageActions = useCallback((actions: ApiKeyPageActions) => {
    setPageActions(actions);
  }, []);
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
        <ManagementPageHeader
            crumbs={false}
            title="API Key Management"
            description="Manage API keys, permissions, allocations and access for applications."
            actions={
              <HStack spacing={2} flexWrap="wrap" justify="flex-end">
                <Button
                  leftIcon={<FiRefreshCw />}
                  size="sm"
                  variant="ghost"
                  onClick={() => pageActions?.refresh()}
                  isLoading={pageActions?.refreshing}
                  isDisabled={!pageActions}
                >
                  Refresh
                </Button>
                <Button
                  leftIcon={<FiSliders />}
                  size="sm"
                  variant="outline"
                  aria-label={BUDGET_COPY.bulkUpdateBudgets}
                  onClick={() => pageActions?.openBulk()}
                  isDisabled={!pageActions || pageActions.bulkDisabled}
                >
                  {BUDGET_COPY.bulkUpdateBudgets}
                </Button>
                <CreateButton onClick={onCreateOpen}>Create API Key</CreateButton>
              </HStack>
            }
          />
          <ApiKeyManagementTab
            isActive
            onCreate={onCreateOpen}
            onBindPageActions={bindPageActions}
            onRegisterRefresh={(refresh) => {
              refreshManagedKeysRef.current = refresh;
            }}
          />
        <FormDrawer
          isOpen={isCreateOpen}
          onClose={requestCloseCreate}
          title="Create API Key"
          description="Create a key, set permissions, and allocate a required budget as a percentage of the application."
          footer={
            <FormActions
              cancelLabel="Cancel"
              submitLabel="Create API Key"
              onCancel={requestCloseCreate}
              submitType="submit"
              form="create-api-key-form"
              isLoading={isCreatingKey}
              loadingText="Creating..."
              justify="space-between"
              pt={0}
            />
          }
        >
          {isCreateOpen ? (
            <CreateApiKeyTab
              tenantId={user.tenant_id}
              onApiKeyCreated={() => void refreshManagedKeysRef.current?.()}
              hideActions
              formId="create-api-key-form"
              onCreatingChange={setIsCreatingKey}
              onCreatedTokenChange={setHasCreatedToken}
            />
          ) : null}
        </FormDrawer>
      </ContentLayout>
    </>
  );
};

export default ApiKeyManagementPage;
