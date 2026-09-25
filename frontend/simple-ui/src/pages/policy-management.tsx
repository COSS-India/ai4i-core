import { Center } from "@chakra-ui/react";
import Head from "next/head";
import React from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import LoadingSpinner from "../components/common/LoadingSpinner";
import PolicyManagement from "../components/policy/PolicyManagement";
import { useAuth } from "../hooks/useAuth";
import { getPlatformName } from "../config/runtimeConfig";
import { isPlatformAdminUser } from "../utils/rbac";
import CreateButton from "../components/common/CreateButton";

const PolicyManagementPage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const openCreateRef = React.useRef<() => void>(() => {});

  const canManagePolicies = isPlatformAdminUser(user?.roles);

  React.useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/auth");
    }
  }, [isAuthenticated, authLoading, router]);

  if (authLoading) {
    return (
      <ContentLayout>
        <Center h="400px">
          <LoadingSpinner size="xl" />
        </Center>
      </ContentLayout>
    );
  }

  if (!isAuthenticated) {
    return (
      <ContentLayout>
        <Center h="400px">
          <LoadingSpinner size="xl" label="Redirecting to sign in…" />
        </Center>
      </ContentLayout>
    );
  }

  return (
    <>
      <Head>
        <title>{`Policy Management - ${getPlatformName()}`}</title>
        <meta
          name="description"
          content="PII policies, type library, and policy-service audit logs"
        />
      </Head>

      <ContentLayout>
        <ManagementPageHeader
          title="Policy Management"
          description="Manage policy definitions and PII types"
          actions={
            canManagePolicies ? (
              <CreateButton onClick={() => openCreateRef.current()}>
                Create Policy
              </CreateButton>
            ) : undefined
          }
        />

        <PolicyManagement
          canManage={canManagePolicies}
          onRegisterCreatePolicy={(open) => {
            openCreateRef.current = open;
          }}
        />
      </ContentLayout>
    </>
  );
};

export default PolicyManagementPage;
