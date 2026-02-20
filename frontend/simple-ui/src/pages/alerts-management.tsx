import {
  Box,
  Center,
  Heading,
  Spinner,
  VStack,
  Text,
} from "@chakra-ui/react";
import Head from "next/head";
import React from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import { useAuth } from "../hooks/useAuth";
import AlertingTab from "../components/profile/AlertingTab";

const AlertsManagementPage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();

  const isAdmin = Boolean(
    user?.roles?.includes("ADMIN") || user?.is_superuser
  );

  React.useEffect(() => {
    if (!authLoading && (!isAuthenticated || !isAdmin)) {
      router.push("/");
    }
  }, [isAuthenticated, authLoading, isAdmin, router]);

  if (authLoading) {
    return (
      <ContentLayout>
        <Center h="400px">
          <Spinner size="xl" color="orange.500" />
        </Center>
      </ContentLayout>
    );
  }

  if (!isAuthenticated || !isAdmin) {
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

  return (
    <>
      <Head>
        <title>Alerts Management - AI4I Platform</title>
        <meta name="description" content="Manage alert definitions, notification receivers, and routing rules" />
      </Head>

      <ContentLayout>
        <Box maxW="7xl" mx="auto" py={8} px={4}>
          <Box mb={8}>
            <Heading
              size="xl"
              color="gray.800"
              userSelect="none"
              cursor="default"
              tabIndex={-1}
            >
              Alerts Management
            </Heading>
            <Text color="gray.500" fontSize="md" mt={2}>
              Define alert policies and configure notification routing for governed, role-aware delivery
            </Text>
          </Box>

          <AlertingTab isActive={true} />
        </Box>
      </ContentLayout>
    </>
  );
};

export default AlertsManagementPage;
