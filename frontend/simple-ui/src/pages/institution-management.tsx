import {
  Box,
  Center,
  Spinner,
  Text,
  VStack,
} from "@chakra-ui/react";
import Head from "next/head";
import React from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import { useAuth } from "../hooks/useAuth";
import TenantManagementTab from "../components/profile/TenantManagementTab";
import { formatInstitutionCopy } from "../utils/institutionCopy";

const InstitutionManagementPage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();

  const isAdmin = Boolean(user?.roles?.includes("ADMIN"));
  const isTenantAdmin = Boolean(
    user?.roles?.some((role) => (role ?? "").trim().toUpperCase() === "TENANT ADMIN")
  );
  const showInstitutionManagement = isAdmin || isTenantAdmin;

  React.useEffect(() => {
    if (!authLoading && (!isAuthenticated || !showInstitutionManagement)) {
      router.push("/");
    }
  }, [isAuthenticated, authLoading, showInstitutionManagement, router]);

  if (authLoading) {
    return (
      <ContentLayout>
        <Center h="400px">
          <Spinner size="xl" color="orange.500" />
        </Center>
      </ContentLayout>
    );
  }

  if (!isAuthenticated || !showInstitutionManagement) {
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
        <title>{formatInstitutionCopy("Tenant Management")} - AI4I Platform</title>
        <meta name="description" content={formatInstitutionCopy("Manage tenants and tenant users")} />
      </Head>

      <ContentLayout>
        <Box maxW="full" mx="auto" py={8} px={4}>
          <ManagementPageHeader
            title="Tenant Management"
            description="Manage tenants and tenant users"
          />
          <TenantManagementTab isActive={true} />
        </Box>
      </ContentLayout>
    </>
  );
};

export default InstitutionManagementPage;
