import { Center } from "@chakra-ui/react";
import Head from "next/head";
import { useRouter } from "next/router";
import React, { useEffect, useRef } from "react";
import { useToastWithDeduplication } from "../utils/toast";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import LoadingSpinner from "../components/common/LoadingSpinner";
import { INSTITUTION } from "../config/constants";
import TierManagement from "../components/tier-management/TierManagement";
import { useAuth } from "../hooks/useAuth";
import { getPlatformName } from "../config/runtimeConfig";
import { isPlatformAdminUser } from "../utils/rbac";
import CreateButton from "../components/common/CreateButton";

const TierManagementPage: React.FC = () => {
  const router = useRouter();
  const toast = useToastWithDeduplication();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const openCreateRef = useRef<() => void>(() => {});

  const isAdmin = isPlatformAdminUser(user?.roles);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      toast({
        title: "Authentication Required",
        description: "Please log in to access Tier Management.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      router.push("/auth");
    }
  }, [authLoading, isAuthenticated, router, toast]);

  useEffect(() => {
    if (!authLoading && isAuthenticated && !isAdmin) {
      toast({
        title: "Access Denied",
        description: "You do not have permission to access Tier Management.",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      router.push("/");
    }
  }, [authLoading, isAuthenticated, isAdmin, router, toast]);

  if (authLoading) {
    return (
      <ContentLayout>
        <Center h="400px">
          <LoadingSpinner size="xl" />
        </Center>
      </ContentLayout>
    );
  }

  if (!isAuthenticated || !isAdmin) {
    return (
      <ContentLayout>
        <Center h="400px">
          <LoadingSpinner size="xl" label="Redirecting..." />
        </Center>
      </ContentLayout>
    );
  }

  return (
    <>
      <Head>
        <title>{`Tier Management - ${getPlatformName()}`}</title>
        <meta name="description" content={`Configure tiers for ${INSTITUTION.toLowerCase()} access`} />
      </Head>

      <ContentLayout>
        <ManagementPageHeader
          title="Tier Management"
          description={`Configure tiers for ${INSTITUTION.toLowerCase()} access`}
          actions={
            <CreateButton onClick={() => openCreateRef.current()}>
              Create Tier
            </CreateButton>
          }
        />

        <TierManagement
          onRegisterCreate={(open) => {
            openCreateRef.current = open;
          }}
        />
      </ContentLayout>
    </>
  );
};

export default TierManagementPage;
