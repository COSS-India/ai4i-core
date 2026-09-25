import {
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
import { CreateModal } from "../components/common/StandardModal";
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
  const onCreateClose = () => {
    setHasCreatedToken(false);
    closeCreate();
  };
  const refreshManagedKeysRef = useRef<(() => Promise<void>) | null>(null);

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
        <title>{`Manage API - ${getPlatformName()}`}</title>
        <meta name="description" content="Create and manage API keys" />
      </Head>

      <ContentLayout>
        <ManagementPageHeader
          title="API Keys"
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
      </ContentLayout>

      <CreateModal
        isOpen={isCreateOpen}
        onClose={onCreateClose}
        lockDismiss={isCreatingKey || hasCreatedToken}
        size="lg"
        title="Create API Key"
        description="Create a key, set permissions, and allocate a required budget as a percentage of the application."
        footer={
          <FormActions
            submitLabel="Create API Key"
            onCancel={onCreateClose}
            submitType="submit"
            form="create-api-key-form"
            isLoading={isCreatingKey}
            loadingText="Creating..."
            justify="space-between"
            pt={0}
          />
        }
      >
        <CreateApiKeyTab
          key={isCreateOpen ? "open" : "closed"}
          tenantId={user.tenant_id}
          onApiKeyCreated={() => void refreshManagedKeysRef.current?.()}
          hideActions
          formId="create-api-key-form"
          onCreatingChange={setIsCreatingKey}
          onCreatedTokenChange={setHasCreatedToken}
        />
      </CreateModal>
    </>
  );
};

export default ApiKeyManagementPage;
