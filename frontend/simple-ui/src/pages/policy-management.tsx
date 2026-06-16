import { Box, Center, Heading, Spinner, Text, VStack } from "@chakra-ui/react";
import Head from "next/head";
import React from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import PolicyManagement from "../components/policy/PolicyManagement";
import { useAuth } from "../hooks/useAuth";

const PolicyManagementPage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();

  const canManagePolicies = Boolean(user?.roles?.includes("ADMIN"));

  React.useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/auth");
    }
  }, [isAuthenticated, authLoading, router]);

  if (authLoading) {
    return (
      <ContentLayout>
        <Center h="400px">
          <Spinner size="xl" color="orange.500" />
        </Center>
      </ContentLayout>
    );
  }

  if (!isAuthenticated) {
    return (
      <ContentLayout>
        <Center h="400px">
          <VStack spacing={4}>
            <Spinner size="xl" color="orange.500" />
            <Text color="gray.600">Redirecting to sign in…</Text>
          </VStack>
        </Center>
      </ContentLayout>
    );
  }

  return (
    <>
      <Head>
        <title>Policy Management - AI4I Platform</title>
        <meta
          name="description"
          content="PII policies, type library, and policy-service audit logs"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={6} w="full">
          <ManagementPageHeader
            title="Policy Management"
            description="Manage policy definitions and PII types"
          />

          <Box maxW="full" w="full" mx="auto" py={4} px={{ base: 2, md: 4 }}>
            <PolicyManagement canManage={canManagePolicies} />
          </Box>
        </VStack>
      </ContentLayout>
    </>
  );
};

export default PolicyManagementPage;
