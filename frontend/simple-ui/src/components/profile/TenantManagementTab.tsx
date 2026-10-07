// Tenant Management tab — backed by auth-service tenant endpoints.

import { useEffect, useMemo, useState } from "react";
import {
  Box,
  useColorModeValue,
  useDisclosure,
  useToast,
} from "@chakra-ui/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  changeTenantTier,
  fetchTenantTiers,
  fetchTiers,
  ACTIVE_TIERS_QUERY_KEY,
  ACTIVE_TIERS_STALE_MS,
  type TenantTierAssignment,
  adjustTenantBudget,
} from "../../services/tierManagementService";
import * as tenantService from "../../services/tenantService";
import { fetchAllServicesMatchingFilters } from "../../services/servicesManagementService";
import { useAuth } from "../../hooks/useAuth";
import { useInferenceTypes } from "../../hooks/useInferenceTypes";
import { useTenantManagement } from "./hooks/useTenantManagement";
import { useOwnInstitutionDetails } from "./hooks/useOwnInstitutionDetails";
import AssignTierModal from "./AssignTierModal";
import { type ServiceMappingsStatus } from "./types";
import {
  INSTITUTION,
  INSTITUTION_ARTICLE,
  TENANT,
  resolveTenantUserDisplayStatus,
} from "../../config/constants";
import { replaceTenantCopy } from "../../utils/replaceTenantCopy";
import {
  isAdopterInstitutionManager,
  isPlatformAdminUser,
} from "../../utils/rbac";
import { useDeferredColumnSort } from "../../utils/tableSort";
import FormActions from "../common/FormActions";
import FormDrawer from "../common/FormDrawer";
import CreateInstitutionForm, {
  CREATE_INSTITUTION_FORM_ID,
} from "./CreateInstitutionForm";
import InstitutionForm from "./InstitutionForm";
import InstitutionUserModal from "../tenant-management/InstitutionUserModal";
import InstitutionConfirmDialogs from "../tenant-management/InstitutionConfirmDialogs";
import ManageTierDrawer from "../tenant-management/ManageTierDrawer";
import {
  budgetWindowToMinDate,
  dateInputToEndOfDayIso,
  dateInputToStartOfDayIso,
  isoToDateInputValue,
  todayDateInputValue,
} from "../../utils/helpers";
import type { TenantUserView, TenantView } from "../../types/tenant";
import { InstitutionAdopterList } from "./InstitutionAdopterList";
import { InstitutionAdminHome } from "./InstitutionAdminHome";
import { InstitutionUsersTable } from "./InstitutionUsersTable";
import { InstitutionWorkspace } from "./InstitutionWorkspace";
import {
  formatRupees,
  resolveTenantTierName,
  resolveTierLabel,
  tenantBudgetNumber,
  type TierOption,
} from "./institutionDisplay";

/** Shown when assigning/reassigning a tier that has no mapped services. */
const TIER_NO_SERVICES_MSG =
  `This Tier has no services mapped. Please map at least one service before assigning to ${INSTITUTION_ARTICLE} ${INSTITUTION.toLowerCase()}.`;

/** UTC calendar day of an instant, as a sortable ordinal. */
const utcDayOrdinal = (d: Date): number =>
  Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());

/**
 * Must stay in step with auth-service's is_budget_window_expired
 * (app/utils/budget_window.py): budget_effective_to is the last usable day,
 * inclusive, so compare UTC calendar DAYS — comparing instants over-expires
 * by up to 24h for any stored value not anchored at 23:59:59.999Z.
 */
function isBudgetAssignmentExpired(tenant: TenantView | null | undefined): boolean {
  if (!tenant?.budget_effective_to) return false;
  const to = new Date(tenant.budget_effective_to);
  if (Number.isNaN(to.getTime())) return false;
  return utcDayOrdinal(new Date()) > utcDayOrdinal(to);
}

// Independent of whether the budget window is live: a lapsed one is fixed in
// the Manage Tier drawer, and the server doesn't gate tier changes on it.
function hasTierAssignment(tenant: TenantView | null | undefined): boolean {
  return Boolean(tenant?.tier_id);
}

export interface TenantManagementTabProps {
  isActive?: boolean;
  onRegisterCreateInstitution?: (open: () => void) => void;
  onInstitutionDetailChange?: (isDetail: boolean) => void;
}

/**
 * Tier filter options, from the tiers the rows carry rather than the catalog
 * alone: the catalog query is ACTIVE-only and cached, so a row can name a tier
 * it does not list. Reusing resolveTenantTierName — the column's own label —
 * keeps the options a superset of what is on screen. Same shape as the Service
 * Registry tier filter.
 */
function buildTierFilterOptions(
  catalog: TierOption[],
  tenants: TenantView[],
  assignmentsByTenantId: Map<string, TenantTierAssignment>,
  pinned: TierOption | null,
): TierOption[] {
  const inCatalog = (id: string) =>
    catalog.some((tier) => String(tier.id) === id);
  const extras = new Map<string, string>();

  for (const tenant of tenants) {
    if (!tenant.tier_id) continue;
    const id = String(tenant.tier_id);
    if (inCatalog(id) || extras.has(id)) continue;
    extras.set(
      id,
      resolveTenantTierName(tenant, catalog, assignmentsByTenantId) ?? id,
    );
  }
  // The selected tier can leave the list under the admin — moving the last
  // tenant off it drops it from both sources — which would blank the select
  // while the filter is still applied. Pinning it keeps the choice visible
  // until it is changed.
  if (pinned && !inCatalog(pinned.id) && !extras.has(pinned.id)) {
    extras.set(pinned.id, pinned.name);
  }

  return [
    ...catalog,
    ...Array.from(extras, ([id, name]) => ({ id, name })).sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { sensitivity: "base" }),
    ),
  ];
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
  onRegisterCreateInstitution,
  onInstitutionDetailChange,
}: TenantManagementTabProps) {
  const { user } = useAuth();
  const tm = useTenantManagement({ user });

  const isAdmin = isPlatformAdminUser(user?.roles);
  const isAdopterManager = isAdopterInstitutionManager(user?.roles);
  const tabCardBg = useColorModeValue("white", "ink.800");
  const tabCardBorder = useColorModeValue("ink.200", "ink.700");
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

  const [tenantConsentAccepted, setTenantConsentAccepted] = useState(false);

  useEffect(() => {
    setTenantConsentAccepted(false);
  }, [tm.isTenantModalOpen]);

  useEffect(() => {
    onRegisterCreateInstitution?.(tm.openTenantModal);
  }, [onRegisterCreateInstitution, tm.openTenantModal]);

  useEffect(() => {
    onInstitutionDetailChange?.(Boolean(tm.tenantDetailView));
  }, [onInstitutionDetailChange, tm.tenantDetailView]);

  const showInstitutionCreate =
    tm.isTenantModalOpen && !tm.isEditTenantModalOpen;

  // Manage plan drawer (change tier + budget top-up/down)
  const {
    isOpen: isManageTierOpen,
    onOpen: onManageTierOpen,
    onClose: onManageTierClose,
  } = useDisclosure();

  // Assign Tier modal — the no-live-assignment half of the same entry point.
  const {
    isOpen: isAssignTierOpen,
    onOpen: onAssignTierOpen,
    onClose: onAssignTierClose,
  } = useDisclosure();

  // Adopter-only: tier drawer + onboard form need tier catalog (ADMIN-only).

  const tiersQuery = useQuery({
    queryKey: ACTIVE_TIERS_QUERY_KEY,
    queryFn: () => fetchTiers(undefined, "ACTIVE"),
    staleTime: ACTIVE_TIERS_STALE_MS,
    enabled: isAdmin,
  });
  // Memoized: the sort accessors and column defs below key off it.
  const tierOptions = useMemo(() => tiersQuery.data?.data ?? [], [tiersQuery.data]);

  // Shared with Tier Management so service↔tier mappings stay consistent
  const servicesForTiersQuery = useQuery({
    queryKey: ["services-for-tiers", enabledTaskTypesParam ?? "all"],
    queryFn: () =>
      fetchAllServicesMatchingFilters({ taskTypes: enabledTaskTypesParam }),
    staleTime: 60_000,
    enabled: isAdmin && (isManageTierOpen || isAssignTierOpen),
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
  const serviceMappingsStatus: ServiceMappingsStatus = serviceMappingsReady
    ? "ready"
    : servicesForTiersQuery.isError
      ? "error"
      : "loading";

  const tenantTiersQuery = useQuery({
    queryKey: ["tenant-tiers"],
    queryFn: () => fetchTenantTiers(),
    staleTime: 2 * 60_000,
    enabled: isAdmin,
  });
  const tenantTierAssignments = tenantTiersQuery.data?.data ?? [];

  const tenantTierAssignmentsById = useMemo(() => {
    const byId = new Map<string, TenantTierAssignment>();
    for (const assignment of tenantTiersQuery.data?.data ?? []) {
      byId.set(String(assignment.tenant_id), assignment);
    }
    return byId;
  }, [tenantTiersQuery.data]);

  /** Remembers the label as it is picked, so a later refetch cannot orphan it. */
  const [pinnedTierFilter, setPinnedTierFilter] = useState<TierOption | null>(
    null,
  );

  const tierFilterOptions = useMemo(
    () =>
      buildTierFilterOptions(
        tierOptions,
        tm.tenants,
        tenantTierAssignmentsById,
        pinnedTierFilter,
      ),
    [tierOptions, tm.tenants, tenantTierAssignmentsById, pinnedTierFilter],
  );

  const handleTierFilterChange = (next: string) => {
    setPinnedTierFilter(
      next === TENANT.TIER_FILTER.ALL || next === TENANT.TIER_FILTER.NONE
        ? null
        : (() => {
            const picked = tierFilterOptions.find(
              (tier) => String(tier.id) === next,
            );
            return picked ? { id: next, name: picked.name } : null;
          })(),
    );
    tm.setTenantFilterTier(next);
  };

  const [viewTierTenant, setViewTierTenant] =
    useState<TenantTierAssignment | null>(null);
  const [manageTenant, setManageTenant] = useState<TenantView | null>(null);
  const [assignTierTenant, setAssignTierTenant] = useState<TenantView | null>(
    null,
  );
  const [manageTierId, setManageTierId] = useState("");
  const [originalTierId, setOriginalTierId] = useState("");
  const [manageBudget, setManageBudget] = useState(0);
  const [isSavingPlan, setIsSavingPlan] = useState(false);
  const [budgetAction, setBudgetAction] = useState<"topup" | "topdown">(
    "topup",
  );
  const [isEditingTier, setIsEditingTier] = useState(false);
  const [budgetAmount, setBudgetAmount] = useState("");
  const [manageEffectiveFrom, setManageEffectiveFrom] = useState("");
  const [manageEffectiveTo, setManageEffectiveTo] = useState("");
  const [originalEffectiveTo, setOriginalEffectiveTo] = useState("");
  const [windowError, setWindowError] = useState<string | null>(null);
  const [managePlanError, setManagePlanError] = useState<string | null>(null);

  const syncTenantAfterPlanChange = async (tenantId: string) => {
    const rows = await tm.handleFetchTenants({ force: true });
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

  const handleTierAssigned = async (tenantId: string) => {
    await queryClient.refetchQueries({ queryKey: ["tenant-tiers"] });
    await syncTenantAfterPlanChange(tenantId);
  };

  const closeAssignTier = () => {
    onAssignTierClose();
    setAssignTierTenant(null);
  };

  const openTenantPlan = (tenant: TenantView) => {
    if (!hasTierAssignment(tenant)) {
      setAssignTierTenant(tenant);
      onAssignTierOpen();
      return;
    }

    const assignment = resolveTenantTierAssignment(
      tenant,
      tenantTierAssignments,
      tierOptions,
    );
    setManageTenant(tenant);
    const tierId = tenant.tier_id ?? assignment?.tier_id ?? "";
    setManageTierId(tierId);
    setOriginalTierId(tierId);
    setIsEditingTier(!tierId);
    setManageBudget(tenantBudgetNumber(tenant) ?? 0);
    setBudgetAmount("");
    setBudgetAction("topup");
    // From is read-only here, so whatever is seeded is what gets sent.
    // Manage Tier always shows the stored From, lapsed window included — a
    // reassignment keeps its original start date. Only Assign Tier, which
    // has no stored window, falls back to today.
    const storedFrom = isoToDateInputValue(tenant.budget_effective_from);
    setManageEffectiveFrom(storedFrom || todayDateInputValue());
    // To keeps the lapsed value so the admin can see what expired, and is
    // the one field they can move.
    setManageEffectiveTo(isoToDateInputValue(tenant.budget_effective_to));
    setOriginalEffectiveTo(isoToDateInputValue(tenant.budget_effective_to));
    setWindowError(null);
    setManagePlanError(null);
    onManageTierOpen();
  };

  const handleCloseManagePlan = () => {
    if (isSavingPlan) return;
    onManageTierClose();
    setManageTenant(null);

    setManageTierId("");
    setOriginalTierId("");
    setIsEditingTier(false);

    setBudgetAmount("");
    setBudgetAction("topup");
    setManageEffectiveFrom("");
    setManageEffectiveTo("");
    setOriginalEffectiveTo("");
    setWindowError(null);
    setManagePlanError(null);
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
    setManagePlanError(null);
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

    setWindowError(null);
    const amountEntered = budgetAmount.trim() !== "";
    const amount = Number(budgetAmount);

    // Mirrors revise_tenant_budget's `window_active` (set AND not expired):
    // a missing or lapsed window is not live, so To has to be (re)set before
    // the revision has a window to attach to.
    const windowActive =
      Boolean(manageTenant.budget_effective_to) &&
      !isBudgetAssignmentExpired(manageTenant);
    // Mirrors the service's `has_existing_window`: AI4IDS-2995 locks From
    // once one is on file at all, lapsed window included (422
    // effective_from_locked if sent), so From only goes out when this call
    // founds the tenant's very first window.
    const hasStoredFrom = Boolean(manageTenant.budget_effective_from);
    const toChanged = manageEffectiveTo !== originalEffectiveTo;

    // From is never user-settable here — openTenantPlan seeds it to the
    // stored window's From, or today when there is no stored window — so
    // only To needs checking.
    if (!windowActive && !manageEffectiveTo) {
      setWindowError(
        "Set a Budget Effective To date to open a new budget window.",
      );
      return;
    }
    if (
      (toChanged || !windowActive) &&
      manageEffectiveFrom &&
      manageEffectiveTo <
        budgetWindowToMinDate(manageEffectiveFrom, todayDateInputValue())
    ) {
      setWindowError(
        "Budget Effective To must be later than today, and at least a day after Budget Effective From.",
      );
      return;
    }

    // A window edit stands on its own — the endpoint takes action/amount and
    // the dates independently, so a date-only revision is a valid call.
    const windowChanged = toChanged || !windowActive;
    if (!amountEntered && !windowChanged) return;
    if (amountEntered && !(amount > 0)) {
      setWindowError("Enter a top-up or top-down amount greater than ₹0.");
      return;
    }

    try {
      const res = await adjustTenantBudget({
        tenant_id: String(manageTenant.tenant_id),
        ...(amountEntered
          ? {
              action: budgetAction === "topup" ? "top-up" : "top-down",
              amount,
            }
          : {}),
        ...(hasStoredFrom
          ? {}
          : {
              budget_effective_from: dateInputToStartOfDayIso(
                manageEffectiveFrom,
              ),
            }),
        ...(windowChanged
          ? { budget_effective_to: dateInputToEndOfDayIso(manageEffectiveTo) }
          : {}),
      });

      const nextBudget = Number(res.allocated_budget);
      if (Number.isFinite(nextBudget)) {
        setManageBudget(nextBudget);
        tm.patchTenantLocal(manageTenant.tenant_id, {
          allocated_budget: nextBudget,
        });
      }
      setBudgetAmount("");
      const committedFrom = isoToDateInputValue(res.budget_effective_from);
      const committedTo = isoToDateInputValue(res.budget_effective_to);
      if (committedFrom) setManageEffectiveFrom(committedFrom);
      if (committedTo) {
        setManageEffectiveTo(committedTo);
        setOriginalEffectiveTo(committedTo);
      }

      // A tenant budget revision never moves any Application's own ₹ (or,
      // therefore, any Key's — keys_recomputed is always literally 0 now
      // and would be misleading to surface). Only each Application's %
      // share of the new total is recalculated; their ₹ allocations are
      // untouched.
      const apps = res.applications_recomputed;
      let description = amountEntered
        ? `Budget ${budgetAction === "topup" ? "increased" : "decreased"} by ${formatRupees(amount)}.`
        : "Budget window updated.";
      if (apps) {
        description += ` ${apps} Application(s)' Budget % ${apps === 1 ? "was" : "were"} recalculated to reflect the new total — their ₹ allocations were not changed.`;
      }

      toast({
        title: amountEntered ? "Budget updated" : "Budget window updated",
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
        title: amountEntered
          ? "Failed to update budget"
          : "Failed to update budget window",
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

  const tenantSortAccessors = useMemo(
    () => ({
      organisation: (t: TenantView) => t.organisation ?? "",
      contact: (t: TenantView) => t.contact_name ?? "",
      email: (t: TenantView) => t.email ?? "",
      // Sort on the rendered label, so the order matches what is on screen.
      tier: (t: TenantView) =>
        resolveTenantTierName(t, tierOptions, tenantTierAssignmentsById) ?? "",
      created: (t: TenantView) =>
        t.created_at ? new Date(t.created_at).getTime() : 0,
    }),
    [tierOptions, tenantTierAssignmentsById],
  );
  const tenantSort = useDeferredColumnSort("organisation", tenantSortAccessors);
  const sortedTenants = useMemo(
    () => tenantSort.apply(tm.filteredTenants),
    [tm.filteredTenants, tenantSort],
  );

  const userSortAccessors = useMemo(
    () => ({
      username: (u: TenantUserView) => u.username ?? u.email ?? "",
      email: (u: TenantUserView) => u.email ?? "",
      full_name: (u: TenantUserView) => u.full_name ?? "",
      created: (u: TenantUserView) => {
        const created = (u as { created_at?: string }).created_at;
        return created ? new Date(created).getTime() : 0;
      },
    }),
    [],
  );
  const userSort = useDeferredColumnSort("username", userSortAccessors);
  const sortedTenantUsers = useMemo(
    () => userSort.apply(tm.filteredTenantUsers),
    [tm.filteredTenantUsers, userSort],
  );

  const usersTable = (
    <InstitutionUsersTable
      tm={tm}
      sortedTenantUsers={sortedTenantUsers}
      userSort={userSort}
      resolveUserDisplayStatus={resolveUserDisplayStatus}
    />
  );

  const closeInstitutionCreate = () => {
    if (tm.isSubmittingTenant) return;
    tm.closeTenantModal();
  };

  const closeInstitutionEdit = () => {
    if (tm.isSubmittingEditTenant) return;
    tm.closeEditTenantModal();
  };


  return (
    <Box>
      {isAdopterManager && !tm.tenantDetailView && (
        <InstitutionAdopterList
          tm={tm}
          sortedTenants={sortedTenants}
          tenantSort={tenantSort}
          isAdmin={isAdmin}
          tierOptions={tierOptions}
          tenantTierAssignmentsById={tenantTierAssignmentsById}
          tierFilterOptions={tierFilterOptions}
          handleTierFilterChange={handleTierFilterChange}
          openTenantPlan={openTenantPlan}
        />
      )}

      {!isAdopterManager && !tm.tenantDetailView && (
        <InstitutionAdminHome
          tabCardBg={tabCardBg}
          tabCardBorder={tabCardBorder}
          ownInstitution={ownInstitution}
          tenantId={user?.tenant_id ?? ""}
          onAddUser={tm.openUserModal}
          usersTable={usersTable}
        />
      )}

      {tm.tenantDetailView && (
        <InstitutionWorkspace
          tm={tm}
          tenant={tm.tenantDetailView}
          tierOptions={tierOptions}
          tenantTierAssignments={tenantTierAssignments}
          usersTable={usersTable}
        />
      )}

      <FormDrawer
        isOpen={showInstitutionCreate}
        onClose={closeInstitutionCreate}
        title={`Create ${INSTITUTION}`}
        description={`Add a new ${INSTITUTION.toLowerCase()} to the platform.`}
        lockDismiss={tm.isSubmittingTenant}
        footer={
          <FormActions
            cancelLabel="Cancel"
            submitLabel={`Create ${INSTITUTION}`}
            onCancel={closeInstitutionCreate}
            submitType="submit"
            form={CREATE_INSTITUTION_FORM_ID}
            isLoading={tm.isSubmittingTenant}
            loadingText="Creating..."
            isDisabled={!tm.canSubmitTenantForm || !tenantConsentAccepted}
            justify="space-between"
            pt={0}
          />
        }
      >
        {showInstitutionCreate ? (
          <CreateInstitutionForm
            tm={tm}
            hideActions
            formId={CREATE_INSTITUTION_FORM_ID}
            onConsentChange={setTenantConsentAccepted}
          />
        ) : null}
      </FormDrawer>

      <FormDrawer
        isOpen={tm.isEditTenantModalOpen}
        onClose={closeInstitutionEdit}
        lockDismiss={tm.isSubmittingEditTenant}
        title={tm.editTenantForm.organisation || `Edit ${INSTITUTION}`}
        description={`Update the ${INSTITUTION.toLowerCase()} details.`}
        footer={
          <FormActions
            cancelLabel="Cancel"
            submitLabel="Save Changes"
            onCancel={closeInstitutionEdit}
            onSubmit={tm.handleSaveEditTenant}
            isLoading={tm.isSubmittingEditTenant}
            isDisabled={!tm.canSubmitEditTenantForm}
            loadingText="Saving..."
            justify="space-between"
            pt={0}
          />
        }
      >
        <InstitutionForm
          mode="edit"
          values={{
            organisation: tm.editTenantForm.organisation ?? "",
            contact_name: tm.editTenantForm.contact_name ?? "",
            email: tm.editTenantForm.email ?? "",
            phone_number: tm.editTenantForm.phone_number ?? "",
          }}
          errors={tm.editTenantFormErrors}
          emailEditable={tm.isEditTenantEmailEditable}
          emailStatus={tm.editTenantEmailStatus}
          onOrganisationChange={tm.handleEditTenantOrganisationChange}
          onOrganisationBlur={tm.handleEditTenantOrganisationBlur}
          onContactNameChange={tm.handleEditTenantContactNameChange}
          onEmailChange={tm.handleEditTenantEmailChange}
          onPhoneChange={tm.handleEditTenantPhoneChange}
        />
      </FormDrawer>
      <InstitutionUserModal
        tm={tm}
        resolveUserDisplayStatus={resolveUserDisplayStatus}
      />
      <InstitutionConfirmDialogs tm={tm} />
      <ManageTierDrawer
        isOpen={isManageTierOpen}
        onClose={handleCloseManagePlan}
        manageTenant={manageTenant}
        managePlanError={managePlanError}
        isEditingTier={isEditingTier}
        setIsEditingTier={setIsEditingTier}
        originalTierId={originalTierId}
        manageTierId={manageTierId}
        setManageTierId={setManageTierId}
        tierOptions={tierOptions}
        serviceMappingsReady={serviceMappingsReady}
        tierIdsWithServices={tierIdsWithServices}
        onCancelTierEdit={handleCancelTierEdit}
        noServicesMessage={TIER_NO_SERVICES_MSG}
        manageBudget={manageBudget}
        manageEffectiveFrom={manageEffectiveFrom}
        manageEffectiveTo={manageEffectiveTo}
        setManageEffectiveTo={setManageEffectiveTo}
        setWindowError={setWindowError}
        windowError={windowError}
        budgetAction={budgetAction}
        setBudgetAction={setBudgetAction}
        budgetAmount={budgetAmount}
        setBudgetAmount={setBudgetAmount}
        onApplyBudget={handleApplyBudget}
        originalEffectiveTo={originalEffectiveTo}
        onSave={handleSaveManagePlan}
        isSavingPlan={isSavingPlan}
        servicesLoading={servicesForTiersQuery.isLoading}
        servicesError={servicesForTiersQuery.isError}
        planExpired={isBudgetAssignmentExpired(manageTenant)}
      />
      <AssignTierModal
        isOpen={isAssignTierOpen}
        onClose={closeAssignTier}
        tenant={assignTierTenant}
        tierOptions={tierOptions}
        tierIdsWithServices={tierIdsWithServices}
        serviceMappingsStatus={serviceMappingsStatus}
        noServicesMessage={TIER_NO_SERVICES_MSG}
        onAssigned={handleTierAssigned}
      />
    </Box>
  );
}
