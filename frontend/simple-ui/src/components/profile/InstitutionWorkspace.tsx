import React from "react";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  Badge,
  Box,
  Button,
  HStack,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Text,
} from "@chakra-ui/react";
import { FiEdit2, FiMail } from "react-icons/fi";
import type { TenantTierAssignment } from "../../services/tierManagementService";
import {
  INSTITUTION,
  TENANT,
  formatTenantStatusLabel,
  getTenantStatusColorScheme,
  isTenantStatus,
} from "../../config/constants";
import { isDefaultTenant } from "../../utils/defaultTenant";
import { fmtDate } from "../../utils/valueFormatters";
import type { TenantView } from "../../types/tenant";
import CreateButton from "../common/CreateButton";
import FormPage from "../common/FormPage";
import FormSection from "../common/FormSection";
import ReadOnlyField from "../common/ReadOnlyField";
import ApplicationManagementTab from "./ApplicationManagementTab";
import InstitutionForm from "./InstitutionForm";
import { useTenantManagement } from "./hooks/useTenantManagement";
import {
  formatRupees,
  resolveTierLabel,
  tenantBudgetNumber,
  type TierOption,
} from "./institutionDisplay";

type TenantManagement = ReturnType<typeof useTenantManagement>;

export function InstitutionWorkspace({
  tm,
  tenant,
  tierOptions,
  tenantTierAssignments,
  usersTable,
}: {
  tm: TenantManagement;
  tenant: TenantView;
  tierOptions: TierOption[];
  tenantTierAssignments: TenantTierAssignment[];
  usersTable: React.ReactNode;
}) {
    const t = tenant;
    const tierAssignment =
      tenantTierAssignments.find(
        (a) => String(a.tenant_id) === String(t.tenant_id),
      ) ?? null;
    return (
      <FormPage
        maxW="full"
        title={t.organisation}
        description="Institution details."
        parent={{
          label: `${INSTITUTION} Management`,
          href: "/institution-management",
          onNavigate: tm.closeTenantDetailView,
        }}
        actions={
          <HStack spacing={2} flexShrink={0} flexWrap="wrap">
            {isDefaultTenant(t) && (
              <Badge colorScheme="purple" textTransform="none">
                Default
              </Badge>
            )}
            <Badge colorScheme={getTenantStatusColorScheme(t.status)}>
              {formatTenantStatusLabel(t.status)}
            </Badge>
            {isTenantStatus(t.status, TENANT.STATUS.PENDING) && (
              <Button
                leftIcon={<FiMail />}
                size="sm"
                variant="outline"
                colorScheme="blue"
                isLoading={tm.resendVerificationTenantId === t.tenant_id}
                loadingText="Sending..."
                onClick={() => void tm.handleResendTenantVerificationEmail(t)}
              >
                Resend Verification Email
              </Button>
            )}
            <Button
              leftIcon={<FiEdit2 />}
              size="sm"
              onClick={() => tm.handleOpenEditTenant(t)}
            >
              Edit
            </Button>
          </HStack>
        }
      >
          <Tabs
            colorScheme="blue"
            variant="enclosed"
            index={
              tm.tenantDetailSubTab === "overview"
                ? 0
                : tm.tenantDetailSubTab === "users"
                  ? 1
                  : 2
            }
            onChange={(idx) =>
              tm.setTenantDetailSubTab(
                idx === 0 ? "overview" : idx === 1 ? "users" : "applications",
              )
            }
          >
            <TabList>
              <Tab fontWeight="semibold">Overview</Tab>
              <Tab fontWeight="semibold">Users</Tab>
              <Tab fontWeight="semibold">Applications</Tab>
            </TabList>
            <TabPanels>
              <TabPanel px={0} pt={6}>
                {isTenantStatus(t.status, TENANT.STATUS.PENDING) && (
                  <Alert
                    status="info"
                    variant="left-accent"
                    borderRadius="md"
                    mb={4}
                  >
                    <AlertIcon />
                    <Box flex="1">
                      <AlertDescription fontSize="sm">
                        This tenant is awaiting activation. The contact must
                        complete the email verification link. If the link
                        expired or was not received, resend it below.
                      </AlertDescription>
                      <Button
                        mt={3}
                        size="sm"
                        leftIcon={<FiMail />}
                        colorScheme="blue"
                        variant="outline"
                        isLoading={
                          tm.resendVerificationTenantId === t.tenant_id
                        }
                        loadingText="Sending..."
                        onClick={() =>
                          void tm.handleResendTenantVerificationEmail(t)
                        }
                      >
                        Resend Verification Email
                      </Button>
                    </Box>
                  </Alert>
                )}
                <InstitutionForm
                  mode="view"
                  showOrganisation={false}
                  values={{
                    organisation: t.organisation,
                    contact_name: t.contact_name ?? "",
                    email: t.email ?? "",
                    phone_number: t.phone_number ?? "",
                  }}
                />
                <FormSection title="Record">
                    <ReadOnlyField label={`${INSTITUTION} ID`}>
                      <Text fontFamily="mono" fontSize="sm">{t.tenant_id}</Text>
                    </ReadOnlyField>
                    <ReadOnlyField label="Status">
                      <Badge colorScheme={getTenantStatusColorScheme(t.status)}>
                        {formatTenantStatusLabel(t.status)}
                      </Badge>
                    </ReadOnlyField>
                    <ReadOnlyField label="Created">{fmtDate(t.created_at)}</ReadOnlyField>
                    <ReadOnlyField label="Tier">
                      {resolveTierLabel(
                        t.tier_id ?? tierAssignment?.tier_id,
                        tierOptions,
                        t.tier_name ?? tierAssignment?.tier_name,
                      )}
                    </ReadOnlyField>
                    <ReadOnlyField label="Budget">
                      {formatRupees(
                        tenantBudgetNumber(t) ??
                          (tierAssignment
                            ? Number(tierAssignment.allocated_budget)
                            : null),
                      )}
                    </ReadOnlyField>
                    {(t.budget_effective_from || t.budget_effective_to) ? (
                      <ReadOnlyField label="Budget period">
                        {fmtDate(t.budget_effective_from)} — {fmtDate(t.budget_effective_to)}
                      </ReadOnlyField>
                    ) : null}
                  </FormSection>
              </TabPanel>
              <TabPanel px={6} pt={6} pb={6}>
                <HStack justify="flex-end" mb={4}>
                  <CreateButton onClick={() => tm.openAddUserForTenant(t.tenant_id)}>
                    Add User
                  </CreateButton>
                </HStack>
                {usersTable}
              </TabPanel>
              <TabPanel px={6} pt={6} pb={6}>
                <ApplicationManagementTab
                  tenantId={t.tenant_id}
                  institutionBudget={
                    tenantBudgetNumber(t) ??
                    (tierAssignment
                      ? Number(tierAssignment.allocated_budget)
                      : null)
                  }
                  currency="INR"
                />
              </TabPanel>
            </TabPanels>
          </Tabs>
      </FormPage>
    );
}
