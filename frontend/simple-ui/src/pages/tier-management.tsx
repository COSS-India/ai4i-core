import { Box, Center, Spinner, Text, VStack } from "@chakra-ui/react";
import Head from "next/head";
import { useRouter } from "next/router";
import React, { useEffect } from "react";
import { useToastWithDeduplication } from "../utils/toast";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import { formatInstitutionCopy } from "../utils/institutionCopy";
import TierManagement from "../components/tier-management/TierManagement";
import { useAuth } from "../hooks/useAuth";
import { useAdminTableSurface } from "../components/common/TableControls";

const TierManagementPage: React.FC = () => {
  const router = useRouter();
  const toast = useToastWithDeduplication();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const { cardBg, borderColor } = useAdminTableSurface();

  const isAdmin = Boolean(user?.roles?.includes("ADMIN"));

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
          <Spinner size="xl" color="blue.500" />
        </Center>
      </ContentLayout>
    );
  }

  if (!isAuthenticated || !isAdmin) {
    return (
      <ContentLayout>
        <Center h="400px">
          <VStack spacing={4}>
            <Spinner size="xl" color="blue.500" />
            <Text color="gray.600">Redirecting...</Text>
          </VStack>
        </Center>
      </ContentLayout>
    );
  }

  return (
    <>
      <Head>
        <title>Tier Management - AI4I Platform</title>
        <meta name="description" content={formatInstitutionCopy("Configure tiers for tenant access")} />
      </Head>

      <ContentLayout>
        <Box maxW="full" mx="auto" py={8} px={6}>
          <ManagementPageHeader
            title="Tier Management"
            description="Configure tiers for tenant access"
          />

          <Box
            mt={6}
            bg={cardBg}
            borderWidth="1px"
            borderColor={borderColor}
            borderRadius="lg"
            p={6}
          >
            <TierManagement />
          </Box>
        </Box>
      </ContentLayout>
    </>
  );
};

export default TierManagementPage;
