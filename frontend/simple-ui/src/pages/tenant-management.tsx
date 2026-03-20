import {
  Box,
  Center,
  Heading,
  Spinner,
  Text,
  VStack,
} from "@chakra-ui/react";
import Head from "next/head";
import React from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import { useAuth } from "../hooks/useAuth";
import TenantManagementTab from "../components/profile/TenantManagementTab";

const TenantManagementPage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();

  const showTenantManagement = Boolean(user?.is_superuser || user?.is_tenant);

  React.useEffect(() => {
    if (!authLoading && (!isAuthenticated || !showTenantManagement)) {
      router.push("/");
    }
  }, [isAuthenticated, authLoading, showTenantManagement, router]);

  if (authLoading) {
    return (
      <ContentLayout>
        <Center h="400px">
          <Spinner size="xl" color="orange.500" />
        </Center>
      </ContentLayout>
    );
  }

  if (!isAuthenticated || !showTenantManagement) {
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
        <title>Tenant Management - AI4I Platform</title>
        <meta name="description" content="Manage tenants and tenant users" />
      </Head>

      <ContentLayout>
        <Box maxW="7xl" mx="auto" py={8} px={4}>
          <TenantManagementTab isActive={true} />
        </Box>
      </ContentLayout>
    </>
  );
};

export default TenantManagementPage;
