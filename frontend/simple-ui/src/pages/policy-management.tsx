import { Center } from "@chakra-ui/react";
import Head from "next/head";
import React from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import LoadingSpinner from "../components/common/LoadingSpinner";
import PolicyManagement from "../components/policy/PolicyManagement";
import { useAuth } from "../hooks/useAuth";
import { getPlatformName } from "../config/runtimeConfig";
import { getTenantIdFromToken } from "../utils/helpers";
import { isPlatformAdminUser, isTenantAdminUser } from "../utils/rbac";
import type { PortalRole } from "../components/policy/pii/model";

const PolicyManagementPage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();

  const role: PortalRole | null = isPlatformAdminUser(user?.roles)
    ? "adopter"
    : isTenantAdminUser(user?.roles)
      ? "institution"
      : null;
  const institutionId = user?.tenant_id?.trim() || getTenantIdFromToken() || "";

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
        <title>{`Policies - ${getPlatformName()}`}</title>
        <meta
          name="description"
          content="Security and privacy policies, PII definitions, and the policy playground"
        />
      </Head>

      <ContentLayout>
          <PolicyManagement role={role} institutionId={institutionId} />
      </ContentLayout>
    </>
  );
};

export default PolicyManagementPage;
