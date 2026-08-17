import { Box, Center, Spinner, Text, VStack } from "@chakra-ui/react";
import Head from "next/head";
import React from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import PiiManagement from "../components/pii/PiiManagement";
import { useAuth } from "../hooks/useAuth";

/**
 * PII Guardrail temporarily removed from UI.
 * To restore: set PII_GUARDRAIL_UI_ENABLED = true, and uncomment related
 * Sidebar / AuthGuard / _app / Header entries.
 */
const PII_GUARDRAIL_UI_ENABLED = false;

const PiiManagementPage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();

  const isAdmin = Boolean(user?.roles?.includes("ADMIN"));

  React.useEffect(() => {
    if (!PII_GUARDRAIL_UI_ENABLED) {
      router.replace("/");
      return;
    }
    if (!authLoading && !isAuthenticated) {
      router.push("/auth");
    }
  }, [isAuthenticated, authLoading, router]);

  if (!PII_GUARDRAIL_UI_ENABLED) {
    return (
      <ContentLayout>
        <Center h="400px">
          <VStack spacing={4}>
            <Spinner size="xl" color="orange.500" />
            <Text color="gray.600">Redirecting...</Text>
          </VStack>
        </Center>
      </ContentLayout>
    );
  }

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
        <title>PII Guardrail - AI4I Platform</title>
        <meta name="description" content="PII detection and policy management" />
      </Head>

      <ContentLayout>
        <Box maxW="full" mx="auto" py={4} px={{ base: 2, md: 4 }}>
          <ManagementPageHeader
            title="PII Guardrail"
            description="Manage PII detection and guardrail rules"
          />
          <PiiManagement isAdmin={isAdmin} />
        </Box>
      </ContentLayout>
    </>
  );
};

export default PiiManagementPage;
