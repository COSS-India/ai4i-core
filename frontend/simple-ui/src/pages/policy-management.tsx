import { Box, Center, Heading, Spinner, Text, VStack } from "@chakra-ui/react";
import Head from "next/head";
import React from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import PolicyManagement from "../components/policy/PolicyManagement";
import { useAuth } from "../hooks/useAuth";

const PolicyManagementPage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();

  const canManagePolicies = Boolean(
    user?.roles?.includes("ADMIN") || user?.is_superuser
  );

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
        <Box maxW="full" mx="auto" py={4} px={{ base: 2, md: 4 }}>
          <Heading size="md" mb={2} color="gray.700">
            Policy Management
          </Heading>
          <Text fontSize="sm" color="gray.600" mb={6}>
            Configure detection policies and the PII type library (policy service). Platform
            administrators only.
          </Text>
          <PolicyManagement canManage={canManagePolicies} />
        </Box>
      </ContentLayout>
    </>
  );
};

export default PolicyManagementPage;
