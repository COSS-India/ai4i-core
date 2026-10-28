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
import type { TenantView } from "../../types/tenant";
import CreateButton from "../common/CreateButton";
import FormPage from "../common/FormPage";
import ApplicationManagementTab from "../profile/ApplicationManagementTab";
import InstitutionOverview from "./InstitutionOverview";
import { useTenantManagement } from "./hooks/useTenantManagement";
import {
  formatRupees,
  resolveTierLabel,
  tenantBudgetNumber,
  type TierOption,
} from "./institutionDisplay";

type TenantManagement = ReturnType<typeof useTenantManagement>;

type DetailSubTab = "overview" | "users" | "applications";

const DETAIL_SUB_TABS: readonly DetailSubTab[] = [
  "overview",
  "users",
  "applications",
];

function detailSubTabIndex(tab: string): number {
  return Math.max(DETAIL_SUB_TABS.indexOf(tab as DetailSubTab), 0);
}

function detailSubTabFromIndex(idx: number): DetailSubTab {
  return DETAIL_SUB_TABS[idx] ?? "applications";
}

type InstitutionWorkspaceProps = Readonly<{
  tm: TenantManagement;
  tenant: TenantView;
  tierOptions: TierOption[];
  tenantTierAssignments: TenantTierAssignment[];
  usersTable: React.ReactNode;
}>;

export function InstitutionWorkspace({
  tm,
  tenant,
  tierOptions,
  tenantTierAssignments,
  usersTable,
}: InstitutionWorkspaceProps) {
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
            index={detailSubTabIndex(tm.tenantDetailSubTab)}
            onChange={(idx) =>
              tm.setTenantDetailSubTab(detailSubTabFromIndex(idx))
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
                <InstitutionOverview
                  tenant={t}
                  tierLabel={resolveTierLabel(
                    t.tier_id ?? tierAssignment?.tier_id,
                    tierOptions,
                    t.tier_name ?? tierAssignment?.tier_name,
                  )}
                  budgetLabel={formatRupees(
                    tenantBudgetNumber(t) ??
                      (tierAssignment
                        ? Number(tierAssignment.allocated_budget)
                        : null),
                  )}
                />
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
