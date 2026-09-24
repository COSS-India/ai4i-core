import { Center } from "@chakra-ui/react";
import Head from "next/head";
import React from "react";
import { useRouter } from "next/router";
import ContentLayout from "../components/common/ContentLayout";
import ManagementPageHeader from "../components/common/ManagementPageHeader";
import CreateButton from "../components/common/CreateButton";
import LoadingSpinner from "../components/common/LoadingSpinner";
import { useAuth } from "../hooks/useAuth";
import TenantManagementTab from "../components/profile/TenantManagementTab";
import { INSTITUTION, INSTITUTIONS } from "../config/constants";
import { getPlatformName } from "../config/runtimeConfig";
import {
  canAccessInstitutionManagement,
  isPlatformAdminUser,
} from "../utils/rbac";

const InstitutionManagementPage: React.FC = () => {
  const router = useRouter();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const openCreateRef = React.useRef<() => void>(() => {});
  const [isInstitutionDetail, setIsInstitutionDetail] = React.useState(false);

  const showInstitutionManagement = canAccessInstitutionManagement(user?.roles);
  const isAdmin = isPlatformAdminUser(user?.roles);

  React.useEffect(() => {
    if (!authLoading && (!isAuthenticated || !showInstitutionManagement)) {
      router.push("/");
    }
  }, [isAuthenticated, authLoading, showInstitutionManagement, router]);

  if (authLoading) {
    return (
      <ContentLayout>
        <Center h="400px">
          <LoadingSpinner size="xl" />
        </Center>
      </ContentLayout>
    );
  }

  if (!isAuthenticated || !showInstitutionManagement) {
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
        <title>{`${INSTITUTION} Management - ${getPlatformName()}`}</title>
        <meta name="description" content={`Manage ${INSTITUTIONS.toLowerCase()} and ${INSTITUTION.toLowerCase()} users`} />
      </Head>

      <ContentLayout>
        <ManagementPageHeader
          title={`${INSTITUTION} Management`}
          description={`Onboard ${INSTITUTIONS.toLowerCase()}, add users, and manage applications from one place.`}
            actions={
              isAdmin && !isInstitutionDetail ? (
                <CreateButton onClick={() => openCreateRef.current()}>
                  Create {INSTITUTION}
                </CreateButton>
              ) : undefined
            }
        />
        <TenantManagementTab
          isActive={true}
          onRegisterCreateInstitution={(open) => {
            openCreateRef.current = open;
          }}
          onInstitutionDetailChange={setIsInstitutionDetail}
        />
      </ContentLayout>
    </>
  );
};

export default InstitutionManagementPage;
