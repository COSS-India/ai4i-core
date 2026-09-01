// Tenant Management tab — backed by auth-service tenant endpoints.

import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  AlertDescription,
  AlertIcon,
  Badge,
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Center,
  Drawer,
  DrawerBody,
  DrawerCloseButton,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerOverlay,
  FormControl,
  FormErrorMessage,
  FormLabel,
  HStack,
  Heading,
  IconButton,
  Input,
  InputGroup,
  InputLeftAddon,
  Modal,
  ModalBody,
  ModalCloseButton,
  ModalContent,
  ModalFooter,
  ModalHeader,
  ModalOverlay,
  Select,
  SimpleGrid,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  Text,
  Tooltip,
  VStack,
  useColorModeValue,
  useDisclosure,
} from "@chakra-ui/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useToast } from "@chakra-ui/react";
import {
  changeTenantTier,
  fetchTenantTiers,
  fetchTiers,
  type TenantTierAssignment,
  adjustTenantBudget,
} from "../../services/tierManagementService";
import * as tenantService from "../../services/tenantService";
import { fetchAllServicesMatchingFilters } from "../../services/servicesManagementService";
import {
  FiArrowLeft,
  FiEdit2,
  FiMail,
  FiPauseCircle,
  FiPlus,
  FiPower,
  FiSliders,
  FiUserPlus,
} from "react-icons/fi";
import {
  ChevronDownIcon,
  DeleteIcon,
  EditIcon,
  ViewIcon,
} from "@chakra-ui/icons";
import { useAuth } from "../../hooks/useAuth";
import { useInferenceTypes } from "../../hooks/useInferenceTypes";
import { useTenantManagement } from "./hooks/useTenantManagement";
import { useOwnInstitutionDetails } from "./hooks/useOwnInstitutionDetails";
import InstitutionDetailsPanel from "./InstitutionDetailsPanel";
import ApplicationManagementTab from "./ApplicationManagementTab";
import ConfirmDialog from "../common/ConfirmDialog";
import ConsentCheckbox, {
  getConsentValidationError,
} from "../common/ConsentCheckbox";
import AdminDataTable, {
  TableSearchField,
  TableSelectField,
  type AdminTableColumn,
} from "../common/AdminDataTable";
import TenantUserRoleBadges from "../common/TenantUserRoleBadges";
import TierSelect from "./TierSelect";
import { TENANT_USER_ROLE_OPTIONS } from "./types";
import {
  INSTITUTION,
  INSTITUTIONS,
  INSTITUTION_ARTICLE,
  TENANT,
  TENANT_STATUS_LIST,
  TENANT_USER_STATUS_LIST,
  formatTenantStatusLabel,
  formatTenantUserStatusLabel,
  getTenantStatusColorScheme,
  isTenantStatus,
  resolveTenantUserDisplayStatus,
} from "../../config/constants";
import { replaceTenantCopy } from "../../utils/replaceTenantCopy";
import {
  isAdopterInstitutionManager,
  isPlatformAdminUser,
} from "../../utils/rbac";
import { FIELD_HINTS } from "../../config/fieldHints";
import FieldHint from "../common/FieldHint";
import {
  DEFAULT_ORG_USER_FORM_ROLE_OPTIONS,
  formatPlatformRoleLabel,
  isDefaultTenant,
} from "../../utils/defaultTenant";
import { dash, fmtDate } from "../../utils/valueFormatters";
import type { TenantUserView, TenantView } from "../../types/tenant";

const BUDGET_MAX_INTEGER_DIGITS = 7;

/** Shown when assigning/reassigning a tier that has no mapped services. */
const TIER_NO_SERVICES_MSG =
  `This Tier has no services mapped. Please map at least one service before assigning to ${INSTITUTION_ARTICLE} ${INSTITUTION.toLowerCase()}.`;

function clampBudgetInput(raw: string): string {
  const dotIndex = raw.indexOf(".");
  const intPart = (dotIndex === -1 ? raw : raw.slice(0, dotIndex)).slice(
    0,
    BUDGET_MAX_INTEGER_DIGITS,
  );
  const decimalPart = dotIndex === -1 ? "" : raw.slice(dotIndex);
  return intPart + decimalPart;
}

export interface TenantManagementTabProps {
  isActive?: boolean;
}

const AVATAR_COLORS = [
  "blue.500",
  "green.500",
  "purple.500",
  "teal.500",
  "orange.500",
  "pink.500",
];

function getTenantInitials(name: string): string {
  const words = name.trim().split(/\s+/);
  if (words.length >= 2) return `${words[0][0]}${words[1][0]}`.toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

function getTenantAvatarBg(name: string): string {
  let sum = 0;
  for (let i = 0; i < name.length; i++) sum += name.codePointAt(i) ?? 0;
  return AVATAR_COLORS[sum % AVATAR_COLORS.length];
}

type TierOption = { id: string; name: string };

function tenantBudgetNumber(t: TenantView): number | null {
  if (t.allocated_budget == null) return null;
  const n = Number(t.allocated_budget);
  return Number.isFinite(n) ? n : null;
}

function resolveTierLabel(
  tierId: string | null | undefined,
  tierOptions: TierOption[],
  fallbackName?: string | null,
): string {
  if (fallbackName?.trim()) return fallbackName.trim();
  if (!tierId) return "—";
  const match = tierOptions.find((tier) => String(tier.id) === String(tierId));
  return match?.name ?? tierId;
}

function formatRupees(amount: number | null | undefined): string {
  if (amount == null) return "—";
  return `₹${amount.toLocaleString("en-IN")}`;
}

function resolveTenantTierAssignment(
  tenant: TenantView,
  assignments: TenantTierAssignment[],
  tierOptions: TierOption[],
): TenantTierAssignment | null {
  const fromList = assignments.find(
    (a) => String(a.tenant_id) === String(tenant.tenant_id),
  );
  if (fromList) return fromList;
  if (!tenant.tier_id) return null;
  return {
    tenant_id: tenant.tenant_id,
    tenant_name: tenant.organisation,
    tier_id: tenant.tier_id,
    tier_name: resolveTierLabel(tenant.tier_id, tierOptions, tenant.tier_name),
    allocated_budget: tenant.allocated_budget ?? 0,
    budget_effective_from: tenant.budget_effective_from ?? undefined,
    budget_effective_to: tenant.budget_effective_to ?? undefined,
    updated_at: tenant.updated_at ?? "",
  };
}

export default function TenantManagementTab({
  isActive = false,
}: TenantManagementTabProps) {
  const { user } = useAuth();
  const tm = useTenantManagement({ user });

  const isAdmin = isPlatformAdminUser(user?.roles);
  const isAdopterManager = isAdopterInstitutionManager(user?.roles);
  const tabCardBg = useColorModeValue("white", "gray.800");
  const tabCardBorder = useColorModeValue("gray.200", "gray.700");
  // Institution Admin view only — idle on the adopter path.
  const ownInstitution = useOwnInstitutionDetails({
    tenantId: user?.tenant_id,
    enabled: !isAdopterManager,
  });
  const { taskTypeNames } = useInferenceTypes();
  const enabledTaskTypesParam =
    taskTypeNames.length > 0 ? taskTypeNames.join(",") : undefined;
  const userListTenantStatus = tm.activeUserListTenant?.status ?? null;

  const resolveUserDisplayStatus = (u: TenantUserView) =>
    resolveTenantUserDisplayStatus(u, userListTenantStatus);

  const toast = useToast();
  const queryClient = useQueryClient();

  // Create Tenant modal — consent checkbox state
  const [tenantConsentAccepted, setTenantConsentAccepted] = useState(false);
  const [tenantConsentError, setTenantConsentError] = useState("");

  // Reset consent whenever the Create Tenant modal opens or closes.
  useEffect(() => {
    setTenantConsentAccepted(false);
    setTenantConsentError("");
  }, [tm.isTenantModalOpen]);

  // Add Tenant User modal — consent checkbox state
  const [userConsentAccepted, setUserConsentAccepted] = useState(false);
  const [userConsentError, setUserConsentError] = useState("");

  // Reset consent whenever the Add Tenant User modal opens or closes.
  useEffect(() => {
    setUserConsentAccepted(false);
    setUserConsentError("");
  }, [tm.isUserModalOpen]);

  // Manage plan drawer (change tier + budget top-up/down)
  const {
    isOpen: isViewTierOpen,
    onOpen: onViewTierOpen,
    onClose: onViewTierClose,
  } = useDisclosure();

  // Adopter-only: tier drawer + onboard form need tier catalog (ADMIN-only).
  const tiersQuery = useQuery({
    queryKey: ["tiers"],
    queryFn: () => fetchTiers(),
    staleTime: 5 * 60_000,
    enabled: isAdmin,
  });
  const tierOptions = tiersQuery.data?.data ?? [];

  // Shared with Tier Management so service↔tier mappings stay consistent
  const servicesForTiersQuery = useQuery({
    queryKey: ["services-for-tiers", enabledTaskTypesParam ?? "all"],
    queryFn: () =>
      fetchAllServicesMatchingFilters({ taskTypes: enabledTaskTypesParam }),
    staleTime: 60_000,
    enabled: isAdmin && (isViewTierOpen || tm.isTenantModalOpen),
  });
  const tierIdsWithServices = useMemo(() => {
    const ids = new Set<string>();
    for (const s of servicesForTiersQuery.data?.items ?? []) {
      for (const tierId of s.tierIds ?? []) {
        if (tierId) ids.add(String(tierId));
      }
    }
    return ids;
  }, [servicesForTiersQuery.data]);
  const serviceMappingsReady = servicesForTiersQuery.isSuccess;

  const tenantTiersQuery = useQuery({
    queryKey: ["tenant-tiers"],
    queryFn: () => fetchTenantTiers(),
    staleTime: 2 * 60_000,
    enabled: isAdmin,
  });
  const tenantTierAssignments = tenantTiersQuery.data?.data ?? [];

  const [viewTierTenant, setViewTierTenant] =
    useState<TenantTierAssignment | null>(null);
  const [manageTenant, setManageTenant] = useState<TenantView | null>(null);
  const [manageTierId, setManageTierId] = useState("");
  const [originalTierId, setOriginalTierId] = useState("");
  const [manageBudget, setManageBudget] = useState(0);
  const [isSavingPlan, setIsSavingPlan] = useState(false);
  const [budgetAction, setBudgetAction] = useState<"topup" | "topdown">(
    "topup",
  );
  const [isEditingTier, setIsEditingTier] = useState(false);
  const [budgetAmount, setBudgetAmount] = useState("");

  const userFormRoleOptions = useMemo(() => {
    const tenantId =
      tm.lockedUserFormTenantId ?? tm.userForm.tenant_id?.trim() ?? "";
    const selected = tm.tenants.find((t) => t.tenant_id === tenantId);
    if (selected && isDefaultTenant(selected)) {
      return DEFAULT_ORG_USER_FORM_ROLE_OPTIONS;
    }
    return TENANT_USER_ROLE_OPTIONS;
  }, [tm.lockedUserFormTenantId, tm.userForm.tenant_id, tm.tenants]);

  const editUserRoleOptions = useMemo((): ReadonlyArray<{
    value: string;
    label: string;
  }> => {
    const tenant = tm.tenants.find(
      (t) => t.tenant_id === tm.editUserForm.tenant_id,
    );
    const isDefaultOrg =
      (tenant && isDefaultTenant(tenant)) ||
      (tm.tenantDetailView && isDefaultTenant(tm.tenantDetailView)) ||
      tm.isDefaultTenantUsersView;
    if (!isDefaultOrg) return TENANT_USER_ROLE_OPTIONS;

    const current = (tm.editUserForm.role || "").trim().toUpperCase();
    if (
      current &&
      !DEFAULT_ORG_USER_FORM_ROLE_OPTIONS.some((o) => o.value === current)
    ) {
      // Preserve non-assignable current roles (e.g. Admin) so profile-only edits
      // do not force a demotion.
      return [
        {
          value: current,
          label: formatPlatformRoleLabel(current),
        },
        ...DEFAULT_ORG_USER_FORM_ROLE_OPTIONS,
      ];
    }
    return DEFAULT_ORG_USER_FORM_ROLE_OPTIONS;
  }, [
    tm.tenants,
    tm.editUserForm.tenant_id,
    tm.editUserForm.role,
    tm.tenantDetailView,
    tm.isDefaultTenantUsersView,
  ]);

  const syncTenantAfterPlanChange = async (tenantId: string) => {
    const rows = await tm.handleFetchTenants();
    const fromList = rows.find((row) => String(row.tenant_id) === String(tenantId));
    let fresh = fromList;
    if (!fresh) {
      try {
        fresh = await tenantService.getViewTenant(tenantId);
      } catch {
        fresh = undefined;
      }
    }
    if (fresh) {
      tm.patchTenantLocal(tenantId, fresh);
      if (manageTenant?.tenant_id === tenantId) {
        setManageTenant(fresh);
        setManageBudget(tenantBudgetNumber(fresh) ?? 0);
      }
    }
  };

  const openManagePlan = (tenant: TenantView) => {
    const assignment = resolveTenantTierAssignment(
      tenant,
      tenantTierAssignments,
      tierOptions,
    );
    setViewTierTenant(assignment);
    setManageTenant(tenant);
    const tierId = tenant.tier_id ?? assignment?.tier_id ?? "";
    setManageTierId(tierId);
    setOriginalTierId(tierId);
    setIsEditingTier(!tierId);
    setManageBudget(tenantBudgetNumber(tenant) ?? 0);
    setBudgetAmount("");
    setBudgetAction("topup");
    onViewTierOpen();
  };

  const handleCloseManagePlan = () => {
    if (isSavingPlan) return;
    onViewTierClose();
    setViewTierTenant(null);
    setManageTenant(null);

    setManageTierId("");
    setOriginalTierId("");
    setIsEditingTier(false);

    setBudgetAmount("");
    setBudgetAction("topup");
  };

  const handleSaveManagePlan = async () => {
    if (!manageTenant || !manageTierId) return;

    if (servicesForTiersQuery.isLoading || servicesForTiersQuery.isFetching) {
      toast({
        title: "Loading services",
        description: "Please wait while service mappings are loaded.",
        status: "info",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    if (servicesForTiersQuery.isError) {
      toast({
        title: "Cannot change tier",
        description:
          "Unable to verify service mappings for this Tier. Please refresh and try again.",
        status: "error",
        duration: 6000,
        isClosable: true,
      });
      return;
    }
    if (!tierIdsWithServices.has(String(manageTierId))) {
      toast({
        title: "Cannot change tier",
        description: TIER_NO_SERVICES_MSG,
        status: "error",
        duration: 6000,
        isClosable: true,
      });
      return;
    }

    setIsSavingPlan(true);
    try {
      await changeTenantTier(String(manageTenant.tenant_id), manageTierId);
      toast({
        title: "Tier updated",
        description: `Tier changed for "${manageTenant.organisation}".`,
        status: "success",
        duration: 4000,
        isClosable: true,
      });
      await queryClient.refetchQueries({ queryKey: ["tenant-tiers"] });
      await syncTenantAfterPlanChange(manageTenant.tenant_id);
      setOriginalTierId(manageTierId);
      setIsEditingTier(false);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })
        ?.response?.data?.detail;
      const message =
        (typeof detail === "object" && detail !== null && "message" in detail
          ? String((detail as { message?: string }).message)
          : undefined) ??
        (typeof detail === "string" ? detail : undefined) ??
        (err instanceof Error ? err.message : "An error occurred.");
      toast({
        title: "Failed to change tier",
        description: replaceTenantCopy(String(message)),
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsSavingPlan(false);
    }
  };

  const handleApplyBudget = async () => {
    if (!manageTenant) return;

    const amount = Number(budgetAmount);
    if (amount <= 0) return;

    try {
      const res = await adjustTenantBudget({
        tenant_id: String(manageTenant.tenant_id),
        action: budgetAction === "topup" ? "top-up" : "top-down",
        amount,
      });

      const nextBudget = Number(res.allocated_budget);
      if (Number.isFinite(nextBudget)) {
        setManageBudget(nextBudget);
        tm.patchTenantLocal(manageTenant.tenant_id, {
          allocated_budget: nextBudget,
        });
      }
      setBudgetAmount("");

      const apps = res.applications_recomputed;
      const keys = res.keys_recomputed;
      let description = `Budget ${budgetAction === "topup" ? "increased" : "decreased"} by ${formatRupees(amount)}.`;
      if (apps != null || keys != null) {
        const parts: string[] = [];
        if (apps != null) parts.push(`${apps} Application(s)`);
        if (keys != null) parts.push(`${keys} Key(s)`);
        if (parts.length > 0) {
          description += ` ${parts.join(" and ")} were automatically adjusted.`;
        }
      }

      toast({
        title: "Budget updated",
        description,
        status: "success",
        duration: 5000,
        isClosable: true,
      });

      await queryClient.refetchQueries({ queryKey: ["tenant-tiers"] });
      await syncTenantAfterPlanChange(manageTenant.tenant_id);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })
        ?.response?.data?.detail;

      toast({
        title: "Failed to update budget",
        description:
          typeof detail === "object" && detail !== null && "message" in detail
            ? String((detail as { message?: string }).message)
            : (typeof detail === "string" ? detail : "Something went wrong."),
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  };

  const handleCancelTierEdit = () => {
    setManageTierId(originalTierId);
    setIsEditingTier(false);
  };

  // Initial fetch when this tab becomes active.
  useEffect(() => {
    if (!isActive || !user) return;
    if (isAdopterManager) {
      void tm.handleFetchTenants();
    } else {
      void tm.handleFetchTenantUsers();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive, user, isAdopterManager]);

  // Refresh users when tenant detail view changes.
  useEffect(() => {
    if (!tm.tenantDetailView) return;
    void tm.handleFetchTenantUsers(tm.tenantDetailView.tenant_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tm.tenantDetailView?.tenant_id]);

  const tenantColumns = useMemo((): AdminTableColumn<TenantView>[] => {
    return [
      {
        id: "organisation",
        header: INSTITUTION,
        thProps: { w: "420px", maxW: "420px" },
        tdProps: { maxW: "420px" },
        cell: (t) => (
          <HStack spacing={3} minW={0}>
            <Center
              w={8}
              h={8}
              borderRadius="full"
              bg={getTenantAvatarBg(t.organisation)}
              color="white"
              fontSize="xs"
              fontWeight="bold"
              flexShrink={0}
            >
              {getTenantInitials(t.organisation)}
            </Center>
            <Tooltip
              label={t.organisation}
              placement="top"
              hasArrow
              openDelay={300}
            >
              <HStack spacing={2} minW={0} maxW="340px">
                <Text fontWeight="medium" fontSize="sm" isTruncated>
                  {t.organisation}
                </Text>
                {isDefaultTenant(t) && (
                  <Badge
                    colorScheme="purple"
                    fontSize="0.65rem"
                    flexShrink={0}
                    textTransform="none"
                  >
                    Default
                  </Badge>
                )}
              </HStack>
            </Tooltip>
          </HStack>
        ),
      },
      {
        id: "contact",
        header: "Contact",
        thProps: { w: "280px", maxW: "280px" },
        tdProps: { maxW: "280px" },
        cell: (t) => (
          <Tooltip
            label={dash(t.contact_name)}
            placement="top"
            hasArrow
            openDelay={300}
          >
            <Text fontSize="sm" isTruncated maxW="260px">
              {dash(t.contact_name)}
            </Text>
          </Tooltip>
        ),
      },
      { id: "email", header: "Email", cell: (t) => dash(t.email) },
      {
        id: "tier",
        header: "Tier",
        cell: (t) => (
          <Text fontSize="sm">
            {resolveTierLabel(t.tier_id, tierOptions, t.tier_name)}
          </Text>
        ),
      },
      {
        id: "budget",
        header: "Budget",
        cell: (t) => (
          <Text fontSize="sm">{formatRupees(tenantBudgetNumber(t))}</Text>
        ),
      },
      {
        id: "status",
        header: "Status",
        cell: (t) => (
          <Badge colorScheme={getTenantStatusColorScheme(t.status)}>
            {formatTenantStatusLabel(t.status)}
          </Badge>
        ),
      },
      {
        id: "created",
        header: "Onboarded",
        cell: (t) => fmtDate(t.created_at),
      },
      {
        id: "actions",
        header: "Actions",
        tdProps: { onClick: (e) => e.stopPropagation() },
        cell: (t) => renderTenantRowActions(t),
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tm, tierOptions]);

  const userColumns = useMemo((): AdminTableColumn<TenantUserView>[] => {
    return [
      {
        id: "username",
        header: "Username",
        cell: (u) => u.username ?? dash(u.email),
      },
      { id: "email", header: "Email", cell: (u) => dash(u.email) },
      { id: "full_name", header: "Full Name", cell: (u) => dash(u.full_name) },
      {
        id: "roles",
        header: "Roles",
        cell: (u) => <TenantUserRoleBadges role={u.role} roles={u.roles} />,
      },
      {
        id: "status",
        header: "Status",
        cell: (u) => (
          <Badge
            colorScheme={getTenantStatusColorScheme(
              resolveUserDisplayStatus(u),
            )}
          >
            {formatTenantUserStatusLabel(resolveUserDisplayStatus(u))}
          </Badge>
        ),
      },
      {
        id: "created",
        header: "Created",
        cell: (u) => fmtDate((u as { created_at?: string }).created_at),
      },
      {
        id: "actions",
        header: "",
        tdProps: { onClick: (e) => e.stopPropagation() },
        cell: (u) => renderUserRowActions(u),
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tm]);

  return (
    <Box>
      {isAdopterManager && !tm.tenantDetailView && renderAdopterView()}

      {!isAdopterManager && !tm.tenantDetailView && renderInstitutionAdminView()}

      {tm.tenantDetailView && renderTenantDetail()}

      {/* Modals always mounted */}
      {renderCreateTenantModal()}
      {renderEditTenantModal()}
      {renderAddUserModal()}
      {renderEditUserModal()}
      {renderViewUserModal()}
      {renderStatusConfirmDialog()}
      {renderDeleteUserDialog()}
      {renderViewTierModal()}
    </Box>
  );

  // ── Tenants list (Adopter Admin) ────────────────────────────────────────
  function renderAdopterView() {
    return (
      <Card>
        <CardHeader>
          <HStack justify="space-between" align="center">
            <Heading size="md">{INSTITUTIONS}</Heading>
            <HStack>
              {isAdmin && (
                <Button
                  leftIcon={<FiPlus />}
                  size="sm"
                  colorScheme="blue"
                  onClick={tm.openTenantModal}
                >
                  Create {INSTITUTION}
                </Button>
              )}
            </HStack>
          </HStack>
        </CardHeader>
        <CardBody>
          <AdminDataTable
            items={tm.filteredTenants}
            columns={tenantColumns}
            getRowKey={(t) => t.tenant_id}
            onRowClick={tm.handleViewTenant}
            isLoading={tm.isLoadingTenants}
            emptyMessage={`No ${INSTITUTIONS.toLowerCase()} found.`}
            noResultsMessage={`No ${INSTITUTIONS.toLowerCase()} match the current filters.`}
            unfilteredCount={tm.tenants.length}
            hasActiveFilters={
              tm.tenantFilterStatus !== "all" || tm.tenantSearch.trim() !== ""
            }
            onClearFilters={() => {
              tm.setTenantFilterStatus("all");
              tm.setTenantSearch("");
            }}
            filters={
              <>
                <TableSearchField
                  placeholder={`Search by organisation or ${INSTITUTION.toLowerCase()} ID`}
                  value={tm.tenantSearch}
                  onChange={tm.setTenantSearch}
                />
                <TableSelectField
                  label="Status"
                  value={tm.tenantFilterStatus}
                  onChange={tm.setTenantFilterStatus}
                  formControlProps={{ w: { base: "full", sm: "200px" } }}
                >
                  <option value="all">All statuses</option>
                  {TENANT_STATUS_LIST.map((s) => (
                    <option key={s} value={s}>
                      {formatTenantStatusLabel(s)}
                    </option>
                  ))}
                </TableSelectField>
              </>
            }
          />
        </CardBody>
      </Card>
    );
  }

  // ── Institution Admin landing view (own institution + its users) ────────
  // One institution, so no list to drill into — tabs are the first screen.
  function renderInstitutionAdminView() {
    return (
      <Card bg={tabCardBg} borderColor={tabCardBorder} borderWidth="1px">
        <Tabs colorScheme="blue" variant="enclosed">
          <TabList>
            <Tab fontWeight="semibold">{`My ${INSTITUTION}`}</Tab>
            <Tab fontWeight="semibold">Users</Tab>
            <Tab fontWeight="semibold">Applications</Tab>
          </TabList>
          <TabPanels>
            <TabPanel px={6} pt={6} pb={6}>
              <InstitutionDetailsPanel
                institution={ownInstitution.institution}
                tierName={ownInstitution.tierName}
                budgetLimit={ownInstitution.budgetLimit}
                currency={ownInstitution.currency}
                isLoading={ownInstitution.isLoading}
                errorMessage={ownInstitution.errorMessage}
                tierBudgetErrorMessage={ownInstitution.tierBudgetErrorMessage}
              />
            </TabPanel>
            <TabPanel px={6} pt={6} pb={6}>{renderTenantView()}</TabPanel>
            <TabPanel px={6} pt={6} pb={6}>
              <ApplicationManagementTab
                tenantId={user?.tenant_id ?? ""}
                institutionBudget={ownInstitution.budgetLimit}
                currency={ownInstitution.currency}
              />
            </TabPanel>
          </TabPanels>
        </Tabs>
      </Card>
    );
  }

  // ── Tenant users list (Tenant Admin or detail view) ─────────────────────
  function renderTenantView() {
    return (
      <Card>
        <CardHeader>
          <HStack justify="space-between" align="center">
            <Heading size="md">{INSTITUTION} Users</Heading>
            <HStack>
              <Button
                leftIcon={<FiUserPlus />}
                size="sm"
                colorScheme="blue"
                onClick={tm.openUserModal}
              >
                Add User
              </Button>
            </HStack>
          </HStack>
        </CardHeader>
        <CardBody>{renderTenantUsersTable()}</CardBody>
      </Card>
    );
  }

  function renderTenantUsersTable() {
    return (
      <AdminDataTable
        key={tm.tenantDetailView?.tenant_id ?? "tenant-users"}
        items={tm.filteredTenantUsers}
        columns={userColumns}
        getRowKey={(u) => u.user_id}
        onRowClick={tm.handleViewUser}
        isLoading={tm.isLoadingTenantUsers}
        emptyMessage={`No users in this ${INSTITUTION.toLowerCase()}.`}
        noResultsMessage="No users match the current filters."
        unfilteredCount={tm.tenantUsers.length}
        hasActiveFilters={
          tm.userFilterStatus !== "all" ||
          tm.userFilterRole !== "all" ||
          tm.userSearch.trim() !== ""
        }
        onClearFilters={tm.handleResetUserFilters}
        filters={
          <>
            <TableSearchField
              placeholder="Search by username, email, or full name"
              value={tm.userSearch}
              onChange={tm.setUserSearch}
            />
            <TableSelectField
              label="Status"
              value={tm.userFilterStatus}
              onChange={tm.setUserFilterStatus}
              formControlProps={{ w: { base: "full", sm: "200px" } }}
            >
              <option value="all">All statuses</option>
              {TENANT_USER_STATUS_LIST.map((s) => (
                <option key={s} value={s}>
                  {formatTenantUserStatusLabel(s)}
                </option>
              ))}
            </TableSelectField>
            <TableSelectField
              label="Role"
              value={tm.userFilterRole}
              onChange={tm.setUserFilterRole}
              formControlProps={{ w: { base: "full", sm: "200px" } }}
            >
              <option value="all">All roles</option>
              {tm.tenantUserRoleFilterOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </TableSelectField>
          </>
        }
      />
    );
  }

  // ── Tenant detail view ──────────────────────────────────────────────────
  function renderTenantDetail() {
    const t = tm.tenantDetailView!;
    const tierAssignment =
      tenantTierAssignments.find(
        (a) => String(a.tenant_id) === String(t.tenant_id),
      ) ?? null;
    return (
      <Card mt={4}>
        <CardHeader>
          <HStack justify="space-between" align="center" flexWrap="wrap">
            <HStack flex="1" minW={0}>
              <IconButton
                aria-label="Back"
                icon={<FiArrowLeft />}
                size="sm"
                variant="ghost"
                onClick={tm.closeTenantDetailView}
                flexShrink={0}
              />
              <Tooltip
                label={t.organisation}
                placement="top"
                hasArrow
                openDelay={300}
              >
                <Heading size="md" isTruncated minW={0}>
                  {t.organisation}
                </Heading>
              </Tooltip>
              {isDefaultTenant(t) && (
                <Badge
                  colorScheme="purple"
                  flexShrink={0}
                  textTransform="none"
                >
                  Default
                </Badge>
              )}
              <Badge
                colorScheme={getTenantStatusColorScheme(t.status)}
                flexShrink={0}
              >
                {formatTenantStatusLabel(t.status)}
              </Badge>
            </HStack>
            <HStack flexShrink={0}>
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
              <Button
                leftIcon={<FiUserPlus />}
                size="sm"
                colorScheme="blue"
                onClick={() => tm.openAddUserForTenant(t.tenant_id)}
              >
                Add User
              </Button>
            </HStack>
          </HStack>
        </CardHeader>
        <CardBody>
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
                <SimpleGrid columns={{ base: 1, md: 2 }} spacing={3}>
                  <Box>
                    <Text fontWeight="semibold">{INSTITUTION} ID</Text>
                    <Text fontFamily="mono">{t.tenant_id}</Text>
                  </Box>
                  <Box>
                    <Text fontWeight="semibold">Status</Text>
                    <Badge colorScheme={getTenantStatusColorScheme(t.status)}>
                      {formatTenantStatusLabel(t.status)}
                    </Badge>
                  </Box>
                  <Box>
                    <Text fontWeight="semibold">Contact Name</Text>
                    <Text wordBreak="break-word">{dash(t.contact_name)}</Text>
                  </Box>
                  <Box>
                    <Text fontWeight="semibold">Email</Text>
                    <Text>{dash(t.email)}</Text>
                  </Box>
                  <Box>
                    <Text fontWeight="semibold">Phone</Text>
                    <Text>{dash(t.phone_number)}</Text>
                  </Box>
                  <Box>
                    <Text fontWeight="semibold">Created</Text>
                    <Text>{fmtDate(t.created_at)}</Text>
                  </Box>
                  <Box>
                    <Text fontWeight="semibold">Tier</Text>
                    <Text>
                      {resolveTierLabel(
                        t.tier_id ?? tierAssignment?.tier_id,
                        tierOptions,
                        t.tier_name ?? tierAssignment?.tier_name,
                      )}
                    </Text>
                  </Box>
                  <Box>
                    <Text fontWeight="semibold">Budget</Text>
                    <Text>
                      {formatRupees(
                        tenantBudgetNumber(t) ??
                          (tierAssignment
                            ? Number(tierAssignment.allocated_budget)
                            : null),
                      )}
                    </Text>
                  </Box>
                  {(t.budget_effective_from || t.budget_effective_to) && (
                    <Box>
                      <Text fontWeight="semibold">Budget period</Text>
                      <Text fontSize="sm">
                        {fmtDate(t.budget_effective_from)} —{" "}
                        {fmtDate(t.budget_effective_to)}
                      </Text>
                    </Box>
                  )}
                </SimpleGrid>
              </TabPanel>
              <TabPanel px={6} pt={6} pb={6}>{renderTenantUsersTable()}</TabPanel>
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
        </CardBody>
      </Card>
    );
  }

  // ── Row actions (inline icons, same pattern as service/model management) ─
  type RowActionMenuItem = {
    key: string;
    label: string;
    onSelect: () => void;
    color: string;
    hoverBg: string;
    icon: React.ReactNode;
    isDisabled?: boolean;
  };

  function renderOverflowActionMenu(
    items: RowActionMenuItem[],
    stopRowClick: (e: React.MouseEvent) => void,
    menuAriaLabel: string,
  ) {
    if (items.length === 0) return null;
    return (
      <Menu>
        <MenuButton
          as={IconButton}
          aria-label={menuAriaLabel}
          icon={<ChevronDownIcon />}
          size="sm"
          variant="ghost"
          colorScheme="gray"
          _hover={{ bg: "gray.100" }}
          onClick={stopRowClick}
        />
        <MenuList minW="auto" w="auto" py={1}>
          {items.map((item) => (
            <Tooltip
              key={item.key}
              label={item.label}
              placement="left"
              hasArrow
              openDelay={300}
            >
              <MenuItem
                aria-label={item.label}
                color={item.color}
                _hover={{ bg: item.hoverBg }}
                isDisabled={item.isDisabled}
                px={2}
                py={2}
                minH="8"
                w="auto"
                onClick={(e) => {
                  stopRowClick(e);
                  item.onSelect();
                }}
              >
                {item.icon}
              </MenuItem>
            </Tooltip>
          ))}
        </MenuList>
      </Menu>
    );
  }

  function renderTenantRowActions(t: TenantView) {
    const stopRowClick = (e: React.MouseEvent) => e.stopPropagation();
    const isProtectedDefaultOrg = isDefaultTenant(t);

    const items: RowActionMenuItem[] = (() => {
      if (isTenantStatus(t.status, TENANT.STATUS.PENDING)) {
        const pendingItems: RowActionMenuItem[] = [
          {
            key: "resend-verification",
            label: "Resend verification email",
            onSelect: () => void tm.handleResendTenantVerificationEmail(t),
            color: "blue.600",
            hoverBg: "blue.50",
            icon: <FiMail size={16} />,
            isDisabled: tm.resendVerificationTenantId === t.tenant_id,
          },
        ];
        if (!isProtectedDefaultOrg) {
          pendingItems.push({
            key: "deactivate",
            label: "Deactivate",
            onSelect: () =>
              tm.handleOpenTenantStatus(t, TENANT.STATUS.DEACTIVATED),
            color: "red.600",
            hoverBg: "red.50",
            icon: <DeleteIcon boxSize={4} />,
          });
        }
        return pendingItems;
      }

      if (isTenantStatus(t.status, TENANT.STATUS.ACTIVE)) {
        if (isProtectedDefaultOrg) return [];
        return [
          {
            key: "suspend",
            label: "Suspend",
            onSelect: () =>
              tm.handleOpenTenantStatus(t, TENANT.STATUS.SUSPENDED),
            color: "orange.600",
            hoverBg: "orange.50",
            icon: <FiPauseCircle size={16} />,
          },
          {
            key: "deactivate",
            label: "Deactivate",
            onSelect: () =>
              tm.handleOpenTenantStatus(t, TENANT.STATUS.DEACTIVATED),
            color: "red.600",
            hoverBg: "red.50",
            icon: <DeleteIcon boxSize={4} />,
          },
        ];
      }

      if (isTenantStatus(t.status, TENANT.STATUS.SUSPENDED)) {
        const suspendedItems: RowActionMenuItem[] = [
          {
            key: "activate",
            label: "Activate",
            onSelect: () => tm.handleOpenTenantStatus(t, TENANT.STATUS.ACTIVE),
            color: "green.600",
            hoverBg: "green.50",
            icon: <FiPower size={16} />,
          },
        ];
        if (!isProtectedDefaultOrg) {
          suspendedItems.push({
            key: "deactivate",
            label: "Deactivate",
            onSelect: () =>
              tm.handleOpenTenantStatus(t, TENANT.STATUS.DEACTIVATED),
            color: "red.600",
            hoverBg: "red.50",
            icon: <DeleteIcon boxSize={4} />,
          });
        }
        return suspendedItems;
      }

      // DEACTIVATED — previous behavior (Activate) unless this tenant was
      // soft-deleted from PENDING verification (terminal, no actions).
      if (tm.isPendingSoftDeletedTenant(t)) {
        return [];
      }
      return [
        {
          key: "activate",
          label: "Activate",
          onSelect: () => tm.handleOpenTenantStatus(t, TENANT.STATUS.ACTIVE),
          color: "green.600",
          hoverBg: "green.50",
          icon: <FiPower size={16} />,
        },
      ];
    })();

    return (
      <HStack spacing={2}>
        <IconButton
          aria-label={`View ${INSTITUTION.toLowerCase()}`}
          icon={<ViewIcon />}
          size="sm"
          variant="ghost"
          colorScheme="blue"
          _hover={{ bg: "blue.50" }}
          onClick={(e) => {
            stopRowClick(e);
            tm.handleViewTenant(t);
          }}
        />
        <IconButton
          aria-label={`Edit ${INSTITUTION.toLowerCase()}`}
          icon={<EditIcon />}
          size="sm"
          variant="ghost"
          colorScheme="green"
          _hover={{ bg: "green.50" }}
          onClick={(e) => {
            stopRowClick(e);
            tm.handleOpenEditTenant(t);
          }}
        />
        <Tooltip label="Manage plan">
          <IconButton
            aria-label="Manage plan"
            icon={<FiSliders size={14} />}
            size="xs"
            w={4}
            h={4}
            minW={4}
            variant="outline"
            colorScheme="blue"
            borderRadius="full"
            _hover={{ bg: "blue.50" }}
            onClick={(e) => {
              stopRowClick(e);
              openManagePlan(t);
            }}
          />
        </Tooltip>

        {renderOverflowActionMenu(items, stopRowClick, `${INSTITUTION} actions`)}
      </HStack>
    );
  }

  function renderUserRowActions(u: TenantUserView) {
    const stopRowClick = (e: React.MouseEvent) => e.stopPropagation();
    const displayStatus = resolveUserDisplayStatus(u);

    const items: RowActionMenuItem[] = (() => {
      if (
        displayStatus === TENANT.USER_STATUS.PENDING ||
        displayStatus === TENANT.USER_STATUS.PENDING_ACTIVATION
      ) {
        return [
          {
            key: "resend-verification",
            label: "Resend setup link",
            onSelect: () => void tm.handleResendTenantUserVerification(u),
            color: "blue.600",
            hoverBg: "blue.50",
            icon: <FiMail size={16} />,
            isDisabled: tm.resendVerificationUserId === u.user_id,
          },
          {
            key: "delete",
            label: "Delete",
            onSelect: () => tm.handleOpenDeleteUser(u),
            color: "red.600",
            hoverBg: "red.50",
            icon: <DeleteIcon boxSize={4} />,
          },
        ];
      }

      if (displayStatus === TENANT.USER_STATUS.ACTIVE) {
        return [
          {
            key: "suspend",
            label: "Suspend",
            onSelect: () =>
              tm.handleOpenUserStatus(u, TENANT.USER_STATUS.SUSPENDED),
            color: "orange.600",
            hoverBg: "orange.50",
            icon: <FiPauseCircle size={16} />,
          },
          {
            key: "delete",
            label: "Delete",
            onSelect: () => tm.handleOpenDeleteUser(u),
            color: "red.600",
            hoverBg: "red.50",
            icon: <DeleteIcon boxSize={4} />,
          },
        ];
      }

      // SUSPENDED
      return [
        {
          key: "activate",
          label: "Activate",
          onSelect: () => tm.handleOpenUserStatus(u, TENANT.USER_STATUS.ACTIVE),
          color: "green.600",
          hoverBg: "green.50",
          icon: <FiPower size={16} />,
        },
        {
          key: "delete",
          label: "Delete",
          onSelect: () => tm.handleOpenDeleteUser(u),
          color: "red.600",
          hoverBg: "red.50",
          icon: <DeleteIcon boxSize={4} />,
        },
      ];
    })();

    return (
      <HStack spacing={2}>
        <IconButton
          aria-label="View user"
          icon={<ViewIcon />}
          size="sm"
          variant="ghost"
          colorScheme="blue"
          _hover={{ bg: "blue.50" }}
          onClick={(e) => {
            stopRowClick(e);
            tm.handleViewUser(u);
          }}
        />
        <IconButton
          aria-label="Edit user"
          icon={<EditIcon />}
          size="sm"
          variant="ghost"
          colorScheme="green"
          _hover={{ bg: "green.50" }}
          onClick={(e) => {
            stopRowClick(e);
            tm.handleOpenEditUser(u);
          }}
        />

        {renderOverflowActionMenu(items, stopRowClick, "User actions")}
      </HStack>
    );
  }

  // ── Modals ─────────────────────────────────────────────────────────────
  function renderCreateTenantModal() {
    return (
      <Modal
        isOpen={tm.isTenantModalOpen}
        onClose={tm.closeTenantModal}
        size="md"
      >
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Create {INSTITUTION}</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={3} align="stretch">
              <FormControl
                isInvalid={Boolean(tm.tenantFormErrors.organisation)}
                isRequired
              >
                <FormLabel>Organisation</FormLabel>
                <Input
                  value={tm.tenantForm.organisation}
                  onChange={(e) =>
                    tm.handleTenantOrganisationChange(e.target.value)
                  }
                  onBlur={(e) =>
                    tm.handleTenantOrganisationBlur(e.target.value)
                  }
                  placeholder={FIELD_HINTS.tenant.organisation.placeholder}
                />
                <FormErrorMessage>
                  {tm.tenantFormErrors.organisation}
                </FormErrorMessage>
                <FieldHint show={!tm.tenantFormErrors.organisation}>
                  {FIELD_HINTS.tenant.organisation.helper}
                </FieldHint>
              </FormControl>
              <FormControl
                isInvalid={Boolean(tm.tenantFormErrors.contact_name)}
                isRequired
              >
                <FormLabel>Contact Name</FormLabel>
                <Input
                  value={tm.tenantForm.contact_name}
                  onChange={(e) =>
                    tm.handleTenantContactNameChange(e.target.value)
                  }
                  onBlur={(e) => tm.handleTenantContactNameBlur(e.target.value)}
                  placeholder={FIELD_HINTS.tenant.contactName.placeholder}
                />
                <FormErrorMessage>
                  {tm.tenantFormErrors.contact_name}
                </FormErrorMessage>
                <FieldHint show={!tm.tenantFormErrors.contact_name}>
                  {FIELD_HINTS.tenant.contactName.helper}
                </FieldHint>
              </FormControl>
              <FormControl
                isInvalid={Boolean(tm.tenantFormErrors.email)}
                isRequired
              >
                <FormLabel>Email</FormLabel>
                <Input
                  type="email"
                  value={tm.tenantForm.email}
                  onChange={(e) => tm.handleTenantEmailChange(e.target.value)}
                  onBlur={tm.handleTenantEmailBlur}
                  placeholder={FIELD_HINTS.tenant.email.placeholder}
                />
                <FormErrorMessage>{tm.tenantFormErrors.email}</FormErrorMessage>
                <FieldHint
                  show={!tm.tenantFormErrors.email}
                  tone={tm.tenantEmailStatus === "available" ? "success" : "muted"}
                >
                  {tm.tenantEmailStatus === "checking"
                    ? FIELD_HINTS.tenant.emailChecking
                    : tm.tenantEmailStatus === "available"
                      ? FIELD_HINTS.tenant.emailAvailable
                      : FIELD_HINTS.tenant.email.helper}
                </FieldHint>
              </FormControl>
              <FormControl
                isInvalid={Boolean(tm.tenantFormErrors.phone_number)}
              >
                <FormLabel>Phone Number</FormLabel>
                <Input
                  value={tm.tenantForm.phone_number}
                  onChange={(e) => tm.handleTenantPhoneChange(e.target.value)}
                  placeholder={FIELD_HINTS.tenant.phone.placeholder}
                />
                <FormErrorMessage>
                  {tm.tenantFormErrors.phone_number}
                </FormErrorMessage>
                <FieldHint show={!tm.tenantFormErrors.phone_number}>
                  {FIELD_HINTS.tenant.phone.helper}
                </FieldHint>
              </FormControl>
              <FormControl>
                <FormLabel>Tier</FormLabel>
                <TierSelect
                  value={tm.tenantForm.tier_id}
                  onChange={(id) =>
                    tm.setTenantForm({ ...tm.tenantForm, tier_id: id })
                  }
                  tierOptions={tierOptions}
                  serviceMappingsReady={serviceMappingsReady}
                  tierIdsWithServices={tierIdsWithServices}
                />
                <FieldHint>{FIELD_HINTS.tenant.onboardTier.helper}</FieldHint>
              </FormControl>
              <FormControl
                isInvalid={Boolean(tm.tenantFormErrors.allocated_budget)}
              >
                <FormLabel>Initial Budget</FormLabel>
                <InputGroup size="sm">
                  <InputLeftAddon>₹</InputLeftAddon>
                  <Input
                    value={tm.tenantForm.allocated_budget}
                    onChange={(e) =>
                      tm.setTenantForm({
                        ...tm.tenantForm,
                        allocated_budget: clampBudgetInput(e.target.value),
                      })
                    }
                    placeholder={FIELD_HINTS.tenant.onboardBudget.placeholder}
                    type="number"
                    min={0}
                    step="any"
                  />
                </InputGroup>
                {tm.tenantFormErrors.allocated_budget && (
                  <FormErrorMessage>
                    {tm.tenantFormErrors.allocated_budget}
                  </FormErrorMessage>
                )}
                <FieldHint show={!tm.tenantFormErrors.allocated_budget}>
                  {FIELD_HINTS.tenant.onboardBudget.helper}
                </FieldHint>
              </FormControl>
              <HStack spacing={4} align="flex-start">
                <FormControl>
                  <FormLabel>Budget effective from</FormLabel>
                  <Input
                    type="date"
                    size="sm"
                    value={tm.tenantForm.budget_effective_from}
                    onChange={(e) =>
                      tm.setTenantForm({
                        ...tm.tenantForm,
                        budget_effective_from: e.target.value,
                      })
                    }
                  />
                  <FieldHint>
                    {FIELD_HINTS.tenant.onboardBudgetEffectiveFrom.helper}
                  </FieldHint>
                </FormControl>
                <FormControl>
                  <FormLabel>Budget effective to</FormLabel>
                  <Input
                    type="date"
                    size="sm"
                    value={tm.tenantForm.budget_effective_to}
                    onChange={(e) =>
                      tm.setTenantForm({
                        ...tm.tenantForm,
                        budget_effective_to: e.target.value,
                      })
                    }
                  />
                  <FieldHint>
                    {FIELD_HINTS.tenant.onboardBudgetEffectiveTo.helper}
                  </FieldHint>
                </FormControl>
              </HStack>
              <ConsentCheckbox
                isChecked={tenantConsentAccepted}
                onChange={(checked) => {
                  setTenantConsentAccepted(checked);
                  if (checked) setTenantConsentError("");
                }}
                error={tenantConsentError}
              />
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button mr={3} variant="ghost" onClick={tm.closeTenantModal}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={() => {
                const consentError = getConsentValidationError(tenantConsentAccepted);
                if (consentError) {
                  setTenantConsentError(consentError);
                  return;
                }
                tm.handleRegisterTenant();
              }}
              isLoading={tm.isSubmittingTenant}
              isDisabled={!tm.canSubmitTenantForm || !tenantConsentAccepted}
            >
              Create
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    );
  }

  function renderEditTenantModal() {
    return (
      <Modal
        isOpen={tm.isEditTenantModalOpen}
        onClose={tm.closeEditTenantModal}
        size="md"
      >
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Edit {INSTITUTION}</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={3} align="stretch">
              <FormControl
                isRequired
                isInvalid={Boolean(tm.editTenantFormErrors.organisation)}
              >
                <FormLabel>Organisation</FormLabel>
                <Input
                  value={tm.editTenantForm.organisation ?? ""}
                  onChange={(e) =>
                    tm.handleEditTenantOrganisationChange(e.target.value)
                  }
                  onBlur={(e) =>
                    tm.handleEditTenantOrganisationBlur(e.target.value)
                  }
                />
                <FormErrorMessage>
                  {tm.editTenantFormErrors.organisation}
                </FormErrorMessage>
                <FieldHint show={!tm.editTenantFormErrors.organisation}>
                  {FIELD_HINTS.tenant.organisation.helper}
                </FieldHint>
              </FormControl>
              <FormControl
                isInvalid={Boolean(tm.editTenantFormErrors.contact_name)}
              >
                <FormLabel>Contact Name</FormLabel>
                <Input
                  value={tm.editTenantForm.contact_name ?? ""}
                  onChange={(e) =>
                    tm.handleEditTenantContactNameChange(e.target.value)
                  }
                />
                <FormErrorMessage>
                  {tm.editTenantFormErrors.contact_name}
                </FormErrorMessage>
                <FieldHint show={!tm.editTenantFormErrors.contact_name}>
                  {FIELD_HINTS.tenant.contactName.helper}
                </FieldHint>
              </FormControl>
              <FormControl
                isRequired={tm.isEditTenantEmailEditable}
                isInvalid={
                  tm.isEditTenantEmailEditable &&
                  Boolean(tm.editTenantFormErrors.email)
                }
              >
                <FormLabel>Email</FormLabel>
                {tm.isEditTenantEmailEditable ? (
                  <>
                    <Input
                      type="email"
                      value={tm.editTenantForm.email ?? ""}
                      onChange={(e) =>
                        tm.handleEditTenantEmailChange(e.target.value)
                      }
                    />
                    <FormErrorMessage>
                      {tm.editTenantFormErrors.email}
                    </FormErrorMessage>
                    <FieldHint show={!tm.editTenantFormErrors.email}>
                      {FIELD_HINTS.tenant.emailVerifyOnChange}
                    </FieldHint>
                    <FieldHint
                      show={
                        !tm.editTenantFormErrors.email &&
                        (tm.editTenantEmailStatus === "checking" ||
                          tm.editTenantEmailStatus === "available")
                      }
                      tone={
                        tm.editTenantEmailStatus === "available" ? "success" : "muted"
                      }
                    >
                      {tm.editTenantEmailStatus === "checking"
                        ? FIELD_HINTS.tenant.emailChecking
                        : FIELD_HINTS.tenant.emailAvailable}
                    </FieldHint>
                  </>
                ) : (
                  <>
                    <Text fontSize="md" color="gray.700" py={1}>
                      {dash(tm.editTenantForm.email)}
                    </Text>
                    <FieldHint>{FIELD_HINTS.tenant.emailPendingOnly}</FieldHint>
                  </>
                )}
              </FormControl>
              <FormControl
                isInvalid={Boolean(tm.editTenantFormErrors.phone_number)}
              >
                <FormLabel>Phone Number</FormLabel>
                <Input
                  value={tm.editTenantForm.phone_number ?? ""}
                  onChange={(e) =>
                    tm.handleEditTenantPhoneChange(e.target.value)
                  }
                />
                <FormErrorMessage>
                  {tm.editTenantFormErrors.phone_number}
                </FormErrorMessage>
                <FieldHint show={!tm.editTenantFormErrors.phone_number}>
                  {FIELD_HINTS.tenant.phone.helper}
                </FieldHint>
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button mr={3} variant="ghost" onClick={tm.closeEditTenantModal}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={tm.handleSaveEditTenant}
              isLoading={tm.isSubmittingEditTenant}
              isDisabled={!tm.canSubmitEditTenantForm}
            >
              Save
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    );
  }

  function renderAddUserModal() {
    return (
      <Modal isOpen={tm.isUserModalOpen} onClose={tm.closeUserModal} size="md">
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Add {INSTITUTION} User</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={3} align="stretch">
              {isAdmin && tm.lockedUserFormTenantId && (
                <FormControl
                  isRequired
                  isInvalid={Boolean(tm.userFormErrors.tenant_id)}
                >
                  <FormLabel>{INSTITUTION}</FormLabel>
                  <Input
                    value={tm.getLockedUserFormTenantLabel()}
                    isReadOnly
                    bg="gray.50"
                    _dark={{ bg: "whiteAlpha.100" }}
                    cursor="not-allowed"
                  />
                  <FormErrorMessage>
                    {tm.userFormErrors.tenant_id}
                  </FormErrorMessage>
                  <FieldHint>{FIELD_HINTS.tenantUser.tenant.helper}</FieldHint>
                </FormControl>
              )}
              {isAdmin && !tm.lockedUserFormTenantId && (
                <FormControl
                  isRequired
                  isInvalid={Boolean(tm.userFormErrors.tenant_id)}
                >
                  <FormLabel>{INSTITUTION}</FormLabel>
                  <Select
                    value={tm.userForm.tenant_id}
                    onChange={(e) => tm.setUserFormTenantId(e.target.value)}
                  >
                    <option value="">Select {INSTITUTION_ARTICLE} {INSTITUTION.toLowerCase()}…</option>
                    {tm.tenants.map((t) => (
                      <option key={t.tenant_id} value={t.tenant_id}>
                        {t.organisation}
                      </option>
                    ))}
                  </Select>
                  <FormErrorMessage>
                    {tm.userFormErrors.tenant_id}
                  </FormErrorMessage>
                </FormControl>
              )}
              <FormControl
                isRequired
                isInvalid={Boolean(tm.userFormErrors.email)}
              >
                <FormLabel>Email</FormLabel>
                <Input
                  type="email"
                  value={tm.userForm.email}
                  onChange={(e) => tm.handleUserEmailChange(e.target.value)}
                  onBlur={tm.handleUserEmailBlur}
                  placeholder={FIELD_HINTS.tenantUser.email.placeholder}
                />
                <FormErrorMessage>{tm.userFormErrors.email}</FormErrorMessage>
                <FieldHint
                  show={!tm.userFormErrors.email}
                  tone={tm.userEmailStatus === "available" ? "success" : "muted"}
                >
                  {tm.userEmailStatus === "checking"
                    ? FIELD_HINTS.tenant.emailChecking
                    : tm.userEmailStatus === "available"
                      ? FIELD_HINTS.tenant.emailAvailable
                      : FIELD_HINTS.tenantUser.email.helper}
                </FieldHint>
              </FormControl>
              <FormControl
                isRequired
                isInvalid={Boolean(tm.userFormErrors.full_name)}
              >
                <FormLabel>Full Name</FormLabel>
                <Input
                  value={tm.userForm.full_name}
                  onChange={(e) => tm.handleUserFullNameChange(e.target.value)}
                  onBlur={(e) => tm.handleUserFullNameBlur(e.target.value)}
                  placeholder={FIELD_HINTS.tenantUser.fullName.placeholder}
                />
                <FormErrorMessage>
                  {tm.userFormErrors.full_name}
                </FormErrorMessage>
                <FieldHint show={!tm.userFormErrors.full_name}>
                  {FIELD_HINTS.tenantUser.fullName.helper}
                </FieldHint>
              </FormControl>
              <FormControl isRequired>
                <FormLabel>Role</FormLabel>
                <Select
                  value={tm.userForm.role}
                  onChange={(e) =>
                    tm.setUserForm({
                      ...tm.userForm,
                      role: e.target.value as typeof tm.userForm.role,
                    })
                  }
                >
                  {userFormRoleOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </Select>
                <FieldHint>{FIELD_HINTS.tenantUser.role.helper}</FieldHint>
              </FormControl>
              <FormControl isInvalid={Boolean(tm.userFormErrors.phone_number)}>
                <FormLabel>Phone Number</FormLabel>
                <Input
                  value={tm.userForm.phone_number}
                  onChange={(e) => tm.handleUserPhoneChange(e.target.value)}
                  placeholder={FIELD_HINTS.tenantUser.phone.placeholder}
                />
                <FormErrorMessage>
                  {tm.userFormErrors.phone_number}
                </FormErrorMessage>
                <FieldHint show={!tm.userFormErrors.phone_number}>
                  {FIELD_HINTS.tenantUser.phone.helper}
                </FieldHint>
              </FormControl>
              <ConsentCheckbox
                isChecked={userConsentAccepted}
                onChange={(checked) => {
                  setUserConsentAccepted(checked);
                  if (checked) setUserConsentError("");
                }}
                error={userConsentError}
              />
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button mr={3} variant="ghost" onClick={tm.closeUserModal}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={() => {
                const consentError = getConsentValidationError(userConsentAccepted);
                if (consentError) {
                  setUserConsentError(consentError);
                  return;
                }
                tm.handleRegisterUser();
              }}
              isLoading={tm.isSubmittingUser}
              isDisabled={!tm.canSubmitUserForm || !userConsentAccepted}
            >
              Add
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    );
  }

  function renderEditUserModal() {
    return (
      <Modal
        isOpen={tm.isEditUserModalOpen}
        onClose={tm.closeEditUserModal}
        size="md"
      >
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>Edit User</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <VStack spacing={3} align="stretch">
              <FormControl
                isRequired
                isInvalid={Boolean(tm.editUserFormErrors.username)}
              >
                <FormLabel>Username</FormLabel>
                <Input
                  value={tm.editUserForm.username ?? ""}
                  onChange={(e) =>
                    tm.handleEditUserUsernameChange(e.target.value)
                  }
                />
                <FormErrorMessage>
                  {tm.editUserFormErrors.username}
                </FormErrorMessage>
                <FieldHint show={!tm.editUserFormErrors.username}>
                  {FIELD_HINTS.tenantUser.username.helper}
                </FieldHint>
              </FormControl>
              <FormControl>
                <FormLabel>Email</FormLabel>
                <Text fontSize="md" color="gray.700" py={1}>
                  {dash(tm.editUserRow?.email)}
                </Text>
                <FieldHint>{FIELD_HINTS.tenantUser.emailLocked}</FieldHint>
              </FormControl>
              <FormControl isInvalid={Boolean(tm.editUserFormErrors.full_name)}>
                <FormLabel>Full Name</FormLabel>
                <Input
                  value={tm.editUserForm.full_name ?? ""}
                  onChange={(e) =>
                    tm.handleEditUserFullNameChange(e.target.value)
                  }
                />
                <FormErrorMessage>
                  {tm.editUserFormErrors.full_name}
                </FormErrorMessage>
                <FieldHint show={!tm.editUserFormErrors.full_name}>
                  {FIELD_HINTS.tenantUser.fullName.helper}
                </FieldHint>
              </FormControl>
              <FormControl isRequired>
                <FormLabel>Role</FormLabel>
                <Select
                  value={tm.editUserForm.role}
                  isDisabled={!tm.editUserRolesLoaded || tm.isEditUserOnlyAdmin}
                  onChange={(e) =>
                    tm.setEditUserForm({
                      ...tm.editUserForm,
                      role: e.target.value as typeof tm.editUserForm.role,
                    })
                  }
                >
                  {editUserRoleOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </Select>
                {!tm.editUserRolesLoaded && (
                  <FieldHint>{FIELD_HINTS.tenantUser.rolesLoadFailed}</FieldHint>
                )}
                {tm.isEditUserOnlyAdmin && (
                  <FieldHint>{FIELD_HINTS.tenantUser.onlyAdminLocked}</FieldHint>
                )}
                {!tm.isEditUserOnlyAdmin && tm.editUserRolesLoaded && (
                  <FieldHint>{FIELD_HINTS.tenantUser.role.helper}</FieldHint>
                )}
              </FormControl>
              <FormControl
                isInvalid={Boolean(tm.editUserFormErrors.phone_number)}
              >
                <FormLabel>Phone Number</FormLabel>
                <Input
                  value={tm.editUserForm.phone_number ?? ""}
                  onChange={(e) => tm.handleEditUserPhoneChange(e.target.value)}
                />
                <FormErrorMessage>
                  {tm.editUserFormErrors.phone_number}
                </FormErrorMessage>
                <FieldHint show={!tm.editUserFormErrors.phone_number}>
                  {FIELD_HINTS.tenantUser.phone.helper}
                </FieldHint>
              </FormControl>
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button mr={3} variant="ghost" onClick={tm.closeEditUserModal}>
              Cancel
            </Button>
            <Button
              colorScheme="blue"
              onClick={tm.handleSaveEditUser}
              isLoading={tm.isSubmittingEditUser}
              isDisabled={!tm.canSubmitEditUserForm}
            >
              Save
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    );
  }

  function renderViewUserModal() {
    const u = tm.viewUserDetail;
    return (
      <Modal
        isOpen={tm.isViewUserModalOpen}
        onClose={tm.closeViewUserModal}
        size="md"
      >
        <ModalOverlay />
        <ModalContent>
          <ModalHeader>User Details</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            {u ? (
              <VStack align="stretch" spacing={3}>
                <Box>
                  <Text fontWeight="semibold">Username</Text>
                  <Text>{u.username}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold">User ID</Text>
                  <Text fontFamily="mono">{u.user_id}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold">Email</Text>
                  <Text>{dash(u.email)}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold">Full Name</Text>
                  <Text>{dash(u.full_name)}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold">Phone</Text>
                  <Text>{dash(u.phone_number)}</Text>
                </Box>
                <Box>
                  <Text fontWeight="semibold">Status</Text>
                  <Badge
                    colorScheme={getTenantStatusColorScheme(
                      resolveUserDisplayStatus(u),
                    )}
                  >
                    {formatTenantUserStatusLabel(resolveUserDisplayStatus(u))}
                  </Badge>
                </Box>
                <Box>
                  <Text fontWeight="semibold">Roles</Text>
                  <TenantUserRoleBadges
                    role={u.role}
                    roles={u.roles}
                    badgeFontSize="sm"
                  />
                </Box>
              </VStack>
            ) : (
              <Text>No user selected.</Text>
            )}
          </ModalBody>
          <ModalFooter>
            <Button onClick={tm.closeViewUserModal}>Close</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    );
  }

  function formatStatusConfirmLabel(
    targetType: "tenant" | "user" | undefined,
    status: string,
  ): string {
    if (targetType === "user") {
      return formatTenantUserStatusLabel(status);
    }
    return formatTenantStatusLabel(status);
  }

  function getTenantStatusConfirmBody(
    currentStatus: string,
    newStatus: string,
  ): string | null {
    if (isTenantStatus(newStatus, TENANT.STATUS.SUSPENDED)) {
      return `API keys become Inactive. Reactivating the ${INSTITUTION.toLowerCase()} restores the same keys to Active.`;
    }
    if (isTenantStatus(newStatus, TENANT.STATUS.DEACTIVATED)) {
      return "API keys are Revoked. After reactivation, an admin must create a new key.";
    }
    if (
      isTenantStatus(newStatus, TENANT.STATUS.ACTIVE) &&
      isTenantStatus(currentStatus, TENANT.STATUS.SUSPENDED)
    ) {
      return "Inactive API keys will automatically resume as Active.";
    }
    if (
      isTenantStatus(newStatus, TENANT.STATUS.ACTIVE) &&
      isTenantStatus(currentStatus, TENANT.STATUS.DEACTIVATED)
    ) {
      return "Previously revoked API keys are not restored. Create a new key if needed.";
    }
    return null;
  }

  function renderStatusConfirmDialog() {
    const target = tm.statusUpdateTarget;
    const isOpen = tm.isStatusDialogOpen && Boolean(target);
    const targetLabel = target?.type === "tenant" ? INSTITUTION.toLowerCase() : "user";
    const statusLabel = formatStatusConfirmLabel(
      target?.type,
      tm.statusUpdateNewStatus,
    );
    const apiKeyNote =
      target?.type === "tenant"
        ? getTenantStatusConfirmBody(
            target.currentStatus,
            tm.statusUpdateNewStatus,
          )
        : null;
    const body = apiKeyNote ? (
      <VStack align="stretch" spacing={2}>
        <Text>Set {targetLabel} status to &quot;{statusLabel}&quot;?</Text>
        <Text>{apiKeyNote}</Text>
      </VStack>
    ) : (
      `Set ${targetLabel} status to "${statusLabel}"?`
    );
    return (
      <ConfirmDialog
        isOpen={isOpen}
        onClose={tm.closeStatusDialog}
        onConfirm={tm.handleConfirmStatusUpdate}
        title={`Change ${targetLabel} status`}
        body={body}
        confirmLabel="Update"
        confirmColorScheme="blue"
        isConfirmLoading={tm.isSubmittingStatus}
      />
    );
  }

  function renderDeleteUserDialog() {
    const target = tm.deleteUserTarget;
    return (
      <ConfirmDialog
        isOpen={tm.isDeleteUserDialogOpen}
        onClose={tm.closeDeleteUserDialog}
        onConfirm={tm.handleConfirmDeleteUser}
        title="Delete user"
        body={`Soft-delete user ${target?.username ?? ""}?`}
        confirmLabel="Delete"
        confirmColorScheme="red"
        isConfirmLoading={tm.isDeletingUser}
      />
    );
  }

  function renderViewTierModal() {
    const hasTierChanged = manageTierId !== originalTierId;
    const manageTierHasNoServices =
      !!manageTierId &&
      serviceMappingsReady &&
      !tierIdsWithServices.has(String(manageTierId));

    const showSaveButton = isEditingTier && hasTierChanged && manageTierId;

    const selectedTierName =
      tierOptions.find((t) => t.id === manageTierId)?.name ?? "";

    return (
      <Drawer
        isOpen={isViewTierOpen}
        onClose={handleCloseManagePlan}
        placement="right"
        size="md"
      >
        <DrawerOverlay />
        <DrawerContent>
          <DrawerCloseButton />
          <DrawerHeader
            fontSize="md"
            fontWeight="semibold"
            borderBottomWidth="1px"
            borderColor="gray.200"
          >
            {`Manage Plan${manageTenant ? ` — ${manageTenant.organisation}` : ""}`}
          </DrawerHeader>
          <DrawerBody py={6}>
            {manageTenant ? (
              <VStack align="stretch" spacing={5}>
                <FormControl>
                  <FormLabel>Tier</FormLabel>
                  {!isEditingTier && originalTierId ? (
                    <HStack>
                      <Input
                        value={selectedTierName || originalTierId}
                        isReadOnly
                        bg="gray.50"
                        flex={1}
                      />

                      <Button size="sm" onClick={() => setIsEditingTier(true)}>
                        Change Tier
                      </Button>
                    </HStack>
                  ) : (
                    <HStack align="flex-start">
                      <TierSelect
                        value={manageTierId}
                        onChange={setManageTierId}
                        tierOptions={tierOptions}
                        serviceMappingsReady={serviceMappingsReady}
                        tierIdsWithServices={tierIdsWithServices}
                        fallbackName={selectedTierName || manageTierId}
                        isInvalid={manageTierHasNoServices}
                        flex={1}
                      />

                      {originalTierId && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={handleCancelTierEdit}
                        >
                          Cancel
                        </Button>
                      )}
                    </HStack>
                  )}
                  {isEditingTier && manageTierHasNoServices && (
                    <FieldHint tone="error">{TIER_NO_SERVICES_MSG}</FieldHint>
                  )}
                </FormControl>

                <FormControl>
                  <FormLabel fontWeight="semibold" fontSize="sm">
                    Current budget (₹)
                  </FormLabel>
                  <Input
                    size="sm"
                    value={manageBudget.toLocaleString("en-IN")}
                    isReadOnly
                    bg="gray.50"
                    cursor="default"
                  />
                </FormControl>
                <FormControl>
                  <Box
                    borderWidth="1px"
                    borderRadius="md"
                    borderColor="gray.200"
                    p={3}
                    bg="gray.50"
                  >
                    <HStack justify="space-between" mb={3}>
                      <Text fontSize="sm" fontWeight="medium">
                        Adjust Budget
                      </Text>

                      <HStack spacing={0}>
                        <Button
                          size="xs"
                          variant={
                            budgetAction === "topup" ? "solid" : "outline"
                          }
                          colorScheme="green"
                          borderRightRadius={0}
                          onClick={() => setBudgetAction("topup")}
                        >
                          + Top-up
                        </Button>

                        <Button
                          size="xs"
                          variant={
                            budgetAction === "topdown" ? "solid" : "outline"
                          }
                          colorScheme="red"
                          borderLeftRadius={0}
                          onClick={() => setBudgetAction("topdown")}
                        >
                          - Top-down
                        </Button>
                      </HStack>
                    </HStack>

                    <HStack>
                      <Input
                        placeholder="Amount in ₹"
                        type="number"
                        value={budgetAmount}
                        onChange={(e) => setBudgetAmount(e.target.value)}
                      />

                      <Button
                        colorScheme="blue"
                        onClick={handleApplyBudget}
                        isDisabled={!budgetAmount}
                      >
                        Apply
                      </Button>
                    </HStack>
                  </Box>

                  <FieldHint mt={3}>
                    {FIELD_HINTS.tenant.planAppliesImmediately}
                  </FieldHint>
                </FormControl>
              </VStack>
            ) : (
              <Text>Select an institution to manage plan.</Text>
            )}
          </DrawerBody>
          <DrawerFooter
            justifyContent="space-between"
            borderTopWidth="1px"
            borderColor="gray.200"
          >
            {showSaveButton && (
              <Button
                colorScheme="blue"
                onClick={handleSaveManagePlan}
                isLoading={isSavingPlan}
                loadingText="Saving..."
                isDisabled={
                  !manageTierId ||
                  manageTierHasNoServices ||
                  servicesForTiersQuery.isLoading ||
                  servicesForTiersQuery.isError
                }
              >
                Change Tier
              </Button>
            )}
          </DrawerFooter>
        </DrawerContent>
      </Drawer>
    );
  }
}
