import { Center } from "@chakra-ui/react";
import Head from "next/head";
import { useRouter } from "next/router";
import React, { useEffect } from "react";
import { useToastWithDeduplication } from "../utils/toast";
import ContentLayout from "../components/common/ContentLayout";
import LoadingSpinner from "../components/common/LoadingSpinner";
import { INSTITUTION } from "../config/constants";
import TierManagement from "../components/tier-management/TierManagement";
import { useAuth } from "../hooks/useAuth";
import { getPlatformName } from "../config/runtimeConfig";
import { isPlatformAdminUser } from "../utils/rbac";

const TierManagementPage: React.FC = () => {
  const router = useRouter();
  const toast = useToastWithDeduplication();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();

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
        <TierManagement />
      </ContentLayout>
    </>
  );
};

export default TierManagementPage;
