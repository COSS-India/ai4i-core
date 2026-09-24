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
  HStack,
  Heading,
  IconButton,
  SimpleGrid,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
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
  ACTIVE_TIERS_QUERY_KEY,
  ACTIVE_TIERS_STALE_MS,
  type TenantTierAssignment,
  adjustTenantBudget,
} from "../../services/tierManagementService";
import * as tenantService from "../../services/tenantService";
import { fetchAllServicesMatchingFilters } from "../../services/servicesManagementService";
import {
  FiArrowLeft,
  FiEdit2,
  FiMail,
} from "react-icons/fi";
import { useAuth } from "../../hooks/useAuth";
import { useInferenceTypes } from "../../hooks/useInferenceTypes";
import { useTenantManagement } from "./hooks/useTenantManagement";
import { useOwnInstitutionDetails } from "./hooks/useOwnInstitutionDetails";
import InstitutionDetailsPanel from "./InstitutionDetailsPanel";
import ApplicationManagementTab from "./ApplicationManagementTab";
import DataTable, {
  DEFAULT_PAGE_SIZE_OPTIONS,
  type DataTableColumn,
} from "../common/table";
import TenantUserRoleBadges from "../common/TenantUserRoleBadges";
import AssignTierModal from "./AssignTierModal";
import { type ServiceMappingsStatus } from "./types";
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
import { useDeferredColumnSort } from "../../utils/tableSort";
import CreateButton from "../common/CreateButton";
import FormActions from "../common/FormActions";
import { CreateModal } from "../common/StandardModal";
import CreateInstitutionForm, {
  CREATE_INSTITUTION_FORM_ID,
} from "./CreateInstitutionForm";
import EditInstitutionModal from "./EditInstitutionModal";
import InstitutionForm from "./InstitutionForm";
import AddInstitutionUserModal from "../tenant-management/AddInstitutionUserModal";
import EditInstitutionUserModal from "../tenant-management/EditInstitutionUserModal";
import ViewInstitutionUserModal from "../tenant-management/ViewInstitutionUserModal";
import InstitutionConfirmDialogs from "../tenant-management/InstitutionConfirmDialogs";
import {
  InstitutionTenantRowActions,
  InstitutionUserRowActions,
} from "../tenant-management/InstitutionRowActions";
import ManageTierDrawer from "../tenant-management/ManageTierDrawer";
import {
  isDefaultTenant,
} from "../../utils/defaultTenant";
import { dash, fmtDate } from "../../utils/valueFormatters";
import {
  budgetWindowToMinDate,
  dateInputToEndOfDayIso,
  dateInputToStartOfDayIso,
  isoToDateInputValue,
  todayDateInputValue,
} from "../../utils/helpers";
import type { TenantUserView, TenantView } from "../../types/tenant";

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

/**
 * Keyed off `tenant.tier_id` alone, the same field the Tier filter matches on,
 * so a row cannot show a tier yet filter as "No tier assigned". The name falls
 * back to the assignment list, which covers a tier newer than the cached catalog.
 */
function resolveTenantTierName(
  tenant: TenantView,
  tierOptions: TierOption[],
  assignmentsByTenantId: Map<string, TenantTierAssignment>,
): string | null {
  const tierId = tenant.tier_id;
  if (!tierId) return null;
  const match = tierOptions.find((tier) => String(tier.id) === String(tierId));
  if (match?.name?.trim()) return match.name.trim();
  const assignment = assignmentsByTenantId.get(String(tenant.tenant_id));
  return assignment?.tier_name?.trim() || tenant.tier_name?.trim() || null;
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

  const tenantColumns = useMemo((): DataTableColumn<TenantView>[] => {
    return [
      {
        id: "organisation",
        header: INSTITUTION,
        thProps: { w: "420px", maxW: "420px" },
        tdProps: { maxW: "420px" },
        sortable: true,
        sortAccessor: (t) => t.organisation ?? "",
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
        sortable: true,
        sortAccessor: (t) => t.contact_name ?? "",
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
      {
        id: "email",
        header: "Email",
        sortable: true,
        sortAccessor: (t) => t.email ?? "",
        cell: (t) => dash(t.email),
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
      // ADMIN-only: both tier queries are gated on `isAdmin`, so anyone else
      // would see a column of dashes reading as "no tier assigned".
      ...((isAdmin
        ? [
            {
              id: "tier",
              header: "Tier",
              thProps: { w: "180px", maxW: "180px" },
              tdProps: { maxW: "180px" },
              sortable: true,
              // Badge treatment mirrors the Service Registry "Tiers" column.
              truncate: false,
              cell: (t) => {
                const name = resolveTenantTierName(
                  t,
                  tierOptions,
                  tenantTierAssignmentsById,
                );
                if (!name) {
                  return (
                    <Text fontSize="sm" color="gray.400">
                      —
                    </Text>
                  );
                }
                return (
                  <Tooltip
                    label={name}
                    placement="top"
                    hasArrow
                    openDelay={300}
                  >
                    <Badge
                      colorScheme="gray"
                      fontSize="xs"
                      px={2}
                      py={0.5}
                      maxW="100%"
                      isTruncated
                    >
                      {name}
                    </Badge>
                  </Tooltip>
                );
              },
            },
          ]
        : []) as DataTableColumn<TenantView>[]),
      {
        id: "created",
        header: "Onboarded",
        sortable: true,
        sortAccessor: (t) =>
          t.created_at ? new Date(t.created_at).getTime() : 0,
        cell: (t) => fmtDate(t.created_at),
      },
      {
        id: "actions",
        header: "Actions",
        tdProps: { onClick: (e) => e.stopPropagation() },
        cell: (t) => (
          <InstitutionTenantRowActions
            tm={tm}
            tenant={t}
            onOpenPlan={openTenantPlan}
          />
        ),
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tm, isAdmin, tierOptions, tenantTierAssignmentsById]);

  const userColumns = useMemo((): DataTableColumn<TenantUserView>[] => {
    return [
      {
        id: "username",
        header: "Username",
        sortable: true,
        sortAccessor: (u) => u.username ?? u.email ?? "",
        cell: (u) => (
          <Text fontWeight="medium" fontSize="sm">
            {u.username ?? dash(u.email)}
          </Text>
        ),
      },
      {
        id: "email",
        header: "Email",
        sortable: true,
        sortAccessor: (u) => u.email ?? "",
        cell: (u) => dash(u.email),
      },
      {
        id: "full_name",
        header: "Full Name",
        sortable: true,
        sortAccessor: (u) => u.full_name ?? "",
        cell: (u) => dash(u.full_name),
      },
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
        sortable: true,
        sortAccessor: (u) => {
          const created = (u as { created_at?: string }).created_at;
          return created ? new Date(created).getTime() : 0;
        },
        cell: (u) => fmtDate((u as { created_at?: string }).created_at),
      },
      {
        id: "actions",
        header: "",
        tdProps: { onClick: (e) => e.stopPropagation() },
        cell: (u) => (
          <InstitutionUserRowActions
            tm={tm}
            user={u}
            resolveUserDisplayStatus={resolveUserDisplayStatus}
          />
        ),
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
      {renderCreateInstitutionModal()}
      <EditInstitutionModal tm={tm} />
      <AddInstitutionUserModal tm={tm} />
      <EditInstitutionUserModal tm={tm} />
      <ViewInstitutionUserModal
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

  // ── Tenants list (Adopter Admin) ────────────────────────────────────────
  function renderAdopterView() {
    return (
          <DataTable
            layout="admin"
            items={sortedTenants}
            columns={tenantColumns}
            getRowKey={(t) => t.tenant_id}
            sort={tenantSort.sort}
            onSortChange={tenantSort.onSortChange}
            onRowClick={tm.handleViewTenant}
            isLoading={tm.isLoadingTenants}
            emptyMessage={`No ${INSTITUTIONS.toLowerCase()} found.`}
            noResultsMessage={`No ${INSTITUTIONS.toLowerCase()} match the current filters.`}
            unfilteredCount={tm.tenants.length}
            hasActiveFilters={
              tm.tenantFilterStatus !== "all" ||
              tm.tenantFilterTier !== TENANT.TIER_FILTER.ALL ||
              tm.tenantSearch.trim() !== ""
            }
            onClearFilters={() => {
              tm.setTenantFilterStatus("all");
              handleTierFilterChange(TENANT.TIER_FILTER.ALL);
              tm.setTenantSearch("");
            }}
            paginate="client"
            paginationPosition="bottom"
            pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
            search={{
              value: tm.tenantSearch,
              onChange: tm.setTenantSearch,
              placeholder: `Search by organisation or ${INSTITUTION.toLowerCase()} ID`,
              fields: ["organisation", "tenant_id"],
            }}
            filterDefs={[
              {
                id: "status",
                label: "Status",
                type: "select",
                param: "status",
                value: tm.tenantFilterStatus,
                onChange: tm.setTenantFilterStatus,
                width: { base: "full", sm: "200px" },
                options: [
                  { label: "All statuses", value: "all" },
                  ...TENANT_STATUS_LIST.map((s) => ({
                    label: formatTenantStatusLabel(s),
                    value: s,
                  })),
                ],
              },
              // ADMIN-only, for the same reason as the Tier column: without
              // the catalog there are no names to populate the options with.
              ...(isAdmin
                ? [
                    {
                      id: "tier",
                      label: "Tier",
                      // Filtered client-side — GET /tenants takes only `status`.
                      type: "select" as const,
                      value: tm.tenantFilterTier,
                      onChange: handleTierFilterChange,
                      width: { base: "full", sm: "200px" },
                      options: [
                        { label: "All tiers", value: TENANT.TIER_FILTER.ALL },
                        ...tierFilterOptions.map((tier) => ({
                          label: tier.name,
                          value: String(tier.id),
                        })),
                        {
                          label: "No tier assigned",
                          value: TENANT.TIER_FILTER.NONE,
                        },
                      ],
                    },
                  ]
                : []),
            ]}
          />
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
      <>
        <HStack justify="flex-end" mb={4}>
          <CreateButton onClick={tm.openUserModal}>Add User</CreateButton>
        </HStack>
        {renderTenantUsersTable()}
      </>
    );
  }

  function renderTenantUsersTable() {
    return (
      <DataTable
        layout="admin"
        key={tm.tenantDetailView?.tenant_id ?? "tenant-users"}
        items={sortedTenantUsers}
        columns={userColumns}
        getRowKey={(u) => u.user_id}
        sort={userSort.sort}
        onSortChange={userSort.onSortChange}
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
        paginate="client"
        paginationPosition="bottom"
        pageSizeOptions={DEFAULT_PAGE_SIZE_OPTIONS}
        search={{
          value: tm.userSearch,
          onChange: tm.setUserSearch,
          placeholder: "Search by username, email, or full name",
          fields: ["username", "email", "full_name"],
        }}
        filterDefs={[
          {
            id: "status",
            label: "Status",
            type: "select",
            param: "status",
            value: tm.userFilterStatus,
            onChange: tm.setUserFilterStatus,
            width: { base: "full", sm: "200px" },
            options: [
              { label: "All statuses", value: "all" },
              ...TENANT_USER_STATUS_LIST.map((s) => ({
                label: formatTenantUserStatusLabel(s),
                value: s,
              })),
            ],
          },
          {
            id: "role",
            label: "Role",
            type: "select",
            param: "role",
            value: tm.userFilterRole,
            onChange: tm.setUserFilterRole,
            width: { base: "full", sm: "200px" },
            options: [
              { label: "All roles", value: "all" },
              ...tm.tenantUserRoleFilterOptions.map((opt) => ({
                label: opt.label,
                value: opt.value,
              })),
            ],
          },
        ]}
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
                <SimpleGrid columns={{ base: 1, md: 2 }} spacing={3} mt={4}>
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
              <TabPanel px={6} pt={6} pb={6}>
                <HStack justify="flex-end" mb={4}>
                  <CreateButton onClick={() => tm.openAddUserForTenant(t.tenant_id)}>
                    Add User
                  </CreateButton>
                </HStack>
                {renderTenantUsersTable()}
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
        </CardBody>
      </Card>
    );
  }

  // ── Modals ─────────────────────────────────────────────────────────────
  function renderCreateInstitutionModal() {
    return (
      <CreateModal
        isOpen={tm.isTenantModalOpen}
        onClose={tm.closeTenantModal}
        size="md"
        title={`Create ${INSTITUTION}`}
        description={`Add a new ${INSTITUTION.toLowerCase()} to the platform.`}
        footer={
          <FormActions
            submitLabel={`Create ${INSTITUTION}`}
            onCancel={tm.closeTenantModal}
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
        <CreateInstitutionForm
          key={tm.isTenantModalOpen ? "open" : "closed"}
          tm={tm}
          hideActions
          formId={CREATE_INSTITUTION_FORM_ID}
          onConsentChange={setTenantConsentAccepted}
        />
      </CreateModal>
    );
  }
}
