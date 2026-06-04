// Tenant Management state + handlers, backed by auth-service tenant endpoints.

import { useState, useMemo, useCallback, useEffect } from "react";
import { forceFrontendSessionEnd } from "../../../hooks/useAuth";
import { useToastWithDeduplication } from "../../../hooks/useToastWithDeduplication";
import authService from "../../../services/authService";
import * as tenantService from "../../../services/tenantService";
import { extractErrorInfo } from "../../../utils/errorHandler";
import {
  collectTenantContactEmails,
  collectUserEmails,
  normalizeEmail,
  validateTenantContactEmail,
  validateTenantUserEmail,
} from "../../../utils/tenantEmailValidation";
import {
  TENANT,
  TENANT_ADMIN_UPDATABLE_STATUSES,
  normalizeTenantStatus,
  resolveTenantUserDisplayStatus,
} from "../../../config/constants";
import type { TenantStatus, TenantUserStatus, TenantView, TenantUserView } from "../../../types/tenant";
import type {
  TenantFormState,
  TenantUserFormState,
  EditTenantFormState,
  EditUserFormState,
  StatusUpdateTargetUnion,
  DeleteUserTarget,
} from "../types";
import {
  normalizeTenantUserRow,
  normalizeTenantUserRoles,
  tenantUserHasRole,
  tenantUserMatchesSearch,
  TENANT_USER_ROLE_FILTER_LIST,
} from "../../../utils/tenantUserRoles";
import {
  DEFAULT_TENANT_PLATFORM_ROLE_FILTER_LIST,
  isDefaultTenant,
} from "../../../utils/defaultTenant";

const USER_EMAIL_PAGE_SIZE = 100;
const DEFAULT_TENANT_USER_ROLE = "USER" as const;

/** Client-side tenant list search: organisation name or tenant ID (substring, case-insensitive). */
function tenantMatchesSearch(t: TenantView, rawSearch: string): boolean {
  const search = rawSearch.trim().toLowerCase();
  if (!search) return true;
  const organisation = (t.organisation ?? "").toLowerCase();
  const tenantId = String(t.tenant_id ?? "").toLowerCase();
  return organisation.includes(search) || tenantId.includes(search);
}

function isTenantAdminRoleForSessionEnd(role?: string): boolean {
  return (role ?? "").trim().toUpperCase() === "TENANT ADMIN";
}

export interface UseTenantManagementOptions {
  user: {
    user_id?: string;
    tenant_id?: string | null;
    roles?: string[];
  } | null;
}

export function useTenantManagement(options: UseTenantManagementOptions) {
  const { user } = options;
  const toast = useToastWithDeduplication();
  const isTenantAdmin = Boolean(user?.roles?.some((role) => isTenantAdminRoleForSessionEnd(role)));
  const isAdmin = Boolean(user?.roles?.includes("ADMIN"));
  const isTenantScopedUser = isTenantAdmin && !isAdmin;
  const userIdStr = user?.user_id ?? null;

  // ----- State -----
  const [tenants, setTenants] = useState<TenantView[]>([]);
  const [tenantUsers, setTenantUsers] = useState<TenantUserView[]>([]);
  const [isLoadingTenants, setIsLoadingTenants] = useState(false);
  const [isLoadingTenantUsers, setIsLoadingTenantUsers] = useState(false);

  const [tenantFilterStatus, setTenantFilterStatus] = useState<string>("all");
  const [tenantSearch, setTenantSearch] = useState("");
  const [userFilterStatus, setUserFilterStatus] = useState<string>("all");
  const [userFilterRole, setUserFilterRole] = useState<string>("all");
  const [userSearch, setUserSearch] = useState("");

  // Create tenant modal
  const [isTenantModalOpen, setIsTenantModalOpen] = useState(false);
  const [tenantForm, setTenantForm] = useState<TenantFormState>({
    organisation: "",
    contact_name: "",
    email: "",
    phone_number: "",
  });
  const [tenantFormErrors, setTenantFormErrors] = useState<Record<string, string>>({});
  const [isSubmittingTenant, setIsSubmittingTenant] = useState(false);
  const [knownTenantEmails, setKnownTenantEmails] = useState<Set<string>>(() => new Set());
  const [knownUserEmails, setKnownUserEmails] = useState<Set<string>>(() => new Set());
  const [isLoadingKnownEmails, setIsLoadingKnownEmails] = useState(false);

  // Add user modal
  const [isUserModalOpen, setIsUserModalOpen] = useState(false);
  const [userForm, setUserForm] = useState<TenantUserFormState>({
    tenant_id: "",
    email: "",
    username: "",
    full_name: "",
    phone_number: "",
    role: DEFAULT_TENANT_USER_ROLE,
  });
  const [isSubmittingUser, setIsSubmittingUser] = useState(false);
  const [userFormErrors, setUserFormErrors] = useState<Record<string, string>>({});
  /** When set, Add User modal tenant is fixed to this tenant (e.g. tenant detail page). */
  const [lockedUserFormTenantId, setLockedUserFormTenantId] = useState<string | null>(null);

  // View user modal (tenant detail uses inline panel via tenantDetailView, not a modal)
  const [viewUserDetail, setViewUserDetail] = useState<TenantUserView | null>(null);
  const [isViewUserModalOpen, setIsViewUserModalOpen] = useState(false);
  const [isLoadingViewUser, setIsLoadingViewUser] = useState(false);

  // Tenant detail sub-view
  const [tenantDetailView, setTenantDetailView] = useState<TenantView | null>(null);
  const [tenantDetailSubTab, setTenantDetailSubTab] = useState<"overview" | "users">("overview");

  // Edit tenant modal
  const [isEditTenantModalOpen, setIsEditTenantModalOpen] = useState(false);
  const [editTenantRow, setEditTenantRow] = useState<TenantView | null>(null);
  const [editTenantForm, setEditTenantForm] = useState<EditTenantFormState>({ tenant_id: "" });
  const [editTenantFormErrors, setEditTenantFormErrors] = useState<Record<string, string>>({});
  const [isSubmittingEditTenant, setIsSubmittingEditTenant] = useState(false);

  // Status update confirmation
  const [statusUpdateTarget, setStatusUpdateTarget] = useState<StatusUpdateTargetUnion | null>(null);
  const [statusUpdateNewStatus, setStatusUpdateNewStatus] = useState<TenantStatus | TenantUserStatus>(
    TENANT.STATUS.ACTIVE
  );
  const [isStatusDialogOpen, setIsStatusDialogOpen] = useState(false);
  const [isSubmittingStatus, setIsSubmittingStatus] = useState(false);

  const [resendVerificationTenantId, setResendVerificationTenantId] = useState<string | null>(
    null
  );

  // Edit user modal
  const [isEditUserModalOpen, setIsEditUserModalOpen] = useState(false);
  const [editUserRow, setEditUserRow] = useState<TenantUserView | null>(null);
  const [editUserForm, setEditUserForm] = useState<EditUserFormState>({
    tenant_id: "",
    user_id: "",
    role: DEFAULT_TENANT_USER_ROLE,
  });
  const [editUserFormErrors, setEditUserFormErrors] = useState<Record<string, string>>({});
  const [isSubmittingEditUser, setIsSubmittingEditUser] = useState(false);

  // Delete user confirmation
  const [deleteUserTarget, setDeleteUserTarget] = useState<DeleteUserTarget | null>(null);
  const [isDeleteUserDialogOpen, setIsDeleteUserDialogOpen] = useState(false);
  const [isDeletingUser, setIsDeletingUser] = useState(false);

  // ----- Derived (filtered lists) -----
  const filteredTenants = useMemo(
    () =>
      tenants.filter((t) => {
        if (
          tenantFilterStatus !== "all" &&
          normalizeTenantStatus(t.status) !== normalizeTenantStatus(tenantFilterStatus)
        ) {
          return false;
        }
        return tenantMatchesSearch(t, tenantSearch);
      }),
    [tenants, tenantFilterStatus, tenantSearch]
  );

  const filteredTenantUsers = useMemo(
    () =>
      tenantUsers.filter((u) => {
        if (userFilterStatus !== "all") {
          const displayStatus = resolveTenantUserDisplayStatus(u);
          if (displayStatus !== userFilterStatus) return false;
        }
        if (userFilterRole !== "all" && !tenantUserHasRole(u, userFilterRole)) {
          return false;
        }
        if (!tenantUserMatchesSearch(u, userSearch)) {
          return false;
        }
        return true;
      }),
    [tenantUsers, userFilterStatus, userFilterRole, userSearch]
  );

  const activeUserListTenant = useMemo(() => {
    if (tenantDetailView) return tenantDetailView;
    if (isTenantScopedUser && user?.tenant_id) {
      return tenants.find((t) => t.tenant_id === user.tenant_id) ?? null;
    }
    return null;
  }, [tenantDetailView, isTenantScopedUser, user?.tenant_id, tenants]);

  const isDefaultTenantUsersView = useMemo(
    () => activeUserListTenant != null && isDefaultTenant(activeUserListTenant),
    [activeUserListTenant]
  );

  const tenantUserRoleFilterOptions = useMemo(
    () =>
      isDefaultTenantUsersView
        ? DEFAULT_TENANT_PLATFORM_ROLE_FILTER_LIST
        : TENANT_USER_ROLE_FILTER_LIST,
    [isDefaultTenantUsersView]
  );

  useEffect(() => {
    setUserFilterRole("all");
  }, [activeUserListTenant?.tenant_id]);

  // ----- Fetchers -----
  const handleFetchTenants = async () => {
    setIsLoadingTenants(true);
    try {
      if (isTenantScopedUser) {
        const tenantId = user?.tenant_id?.trim();
        if (!tenantId) {
          setTenants([]);
          return;
        }
        const tenant = await tenantService.getViewTenant(tenantId);
        setTenants(tenant ? [tenant] : []);
        return;
      }
      const res = await tenantService.listTenants();
      const rows = res.tenants ?? [];
      setTenants(rows);
      setKnownTenantEmails(collectTenantContactEmails(rows));
    } catch (err) {
      console.error("Failed to fetch tenants:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 8000 });
      setTenants([]);
    } finally {
      setIsLoadingTenants(false);
    }
  };

  const loadTenantUsersForTenant = async (tenantId: string): Promise<TenantUserView[]> => {
    const res = await tenantService.listUsers(tenantId);
    return normalizeTenantUserRoles(res.users ?? []);
  };

  const handleFetchTenantUsers = async (tenantIdOverride?: string) => {
    const tenantId = tenantIdOverride ?? tenantDetailView?.tenant_id ?? user?.tenant_id ?? null;
    if (!tenantId) {
      toast({
        title: "Tenant context missing",
        description: "Unable to load users because no tenant ID is available.",
        status: "warning",
        isClosable: true,
        duration: 5000,
      });
      setTenantUsers([]);
      return;
    }
    setIsLoadingTenantUsers(true);
    try {
      const users = await loadTenantUsersForTenant(tenantId);
      setTenantUsers(users);
      setKnownUserEmails(collectUserEmails(users));
    } catch (err) {
      console.error("Failed to fetch tenant users:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 8000 });
      setTenantUsers([]);
    } finally {
      setIsLoadingTenantUsers(false);
    }
  };

  const refreshTenantAndUserLists = async (tenantIdOverride?: string) => {
    if (isAdmin) {
      await handleFetchTenants();
    }
    const tenantId = tenantIdOverride ?? tenantDetailView?.tenant_id ?? user?.tenant_id ?? null;
    if (tenantId) {
      await handleFetchTenantUsers(tenantId);
    }
  };

  const handleResetTenantFilters = () => {
    setTenantFilterStatus("all");
    setTenantSearch("");
    setUserFilterStatus("all");
    setUserFilterRole("all");
    setUserSearch("");
  };

  const handleResetUserFilters = () => {
    setUserFilterStatus("all");
    setUserFilterRole("all");
    setUserSearch("");
  };

  const syncKnownEmailsFromLists = useCallback(
    (tenantRows: TenantView[], userRows: TenantUserView[]) => {
      setKnownTenantEmails(collectTenantContactEmails(tenantRows));
      setKnownUserEmails(collectUserEmails(userRows));
    },
    []
  );

  /** Load tenant contact + user emails for client-side uniqueness checks. */
  const refreshKnownAccountEmails = useCallback(async () => {
    setIsLoadingKnownEmails(true);
    try {
      let tenantRows: TenantView[] = tenants;
      if (isAdmin) {
        tenantRows = (await tenantService.listTenants()).tenants ?? [];
      } else {
        const tenantId = user?.tenant_id?.trim();
        if (tenantId) {
          const own = await tenantService.getViewTenant(tenantId);
          tenantRows = own ? [own] : [];
        }
      }
      const tenantEmailSet = collectTenantContactEmails(tenantRows);
      const userEmailSet = new Set<string>(collectUserEmails(tenantUsers));

      let offset = 0;
      for (;;) {
        const batch = await authService.listUsersPage(offset, USER_EMAIL_PAGE_SIZE);
        for (const u of batch) {
          const e = (u.email ?? "").trim().toLowerCase();
          if (e) userEmailSet.add(e);
        }
        if (batch.length < USER_EMAIL_PAGE_SIZE) break;
        offset += USER_EMAIL_PAGE_SIZE;
      }

      setKnownTenantEmails(tenantEmailSet);
      setKnownUserEmails(userEmailSet);
    } catch (err) {
      console.error("Failed to load emails for uniqueness check:", err);
      syncKnownEmailsFromLists(tenants, tenantUsers);
    } finally {
      setIsLoadingKnownEmails(false);
    }
  }, [isAdmin, user?.tenant_id, tenants, tenantUsers, syncKnownEmailsFromLists]);

  // ----- Create tenant -----
  const openTenantModal = () => {
    setTenantForm({ organisation: "", contact_name: "", email: "", phone_number: "" });
    setTenantFormErrors({});
    setIsTenantModalOpen(true);
    void refreshKnownAccountEmails();
  };

  const closeTenantModal = () => {
    setIsTenantModalOpen(false);
  };

  const handleRegisterTenant = async () => {
    const errors: Record<string, string> = {};
    if (!tenantForm.organisation.trim()) errors.organisation = "Organisation is required.";
    if (!tenantForm.contact_name.trim()) errors.contact_name = "Contact name is required.";
    const emailError = validateTenantContactEmail(
      tenantForm.email,
      knownTenantEmails,
      knownUserEmails
    );
    if (emailError) errors.email = emailError;
    if (Object.keys(errors).length > 0) {
      setTenantFormErrors(errors);
      toast({
        title: "Validation",
        description: Object.values(errors)[0],
        status: "error",
        isClosable: true,
      });
      return;
    }
    setTenantFormErrors({});
    setIsSubmittingTenant(true);
    try {
      const created = await tenantService.registerTenant({
        organisation: tenantForm.organisation.trim(),
        contact_name: tenantForm.contact_name.trim(),
        email: tenantForm.email.trim(),
        phone_number: tenantForm.phone_number.trim() || undefined,
      });
      toast({
        title: "Tenant created",
        description: `${created.organisation} is pending activation. The contact will receive a setup link by email.`,
        status: "success",
        duration: 5000,
        isClosable: true,
      });
      closeTenantModal();
      await refreshTenantAndUserLists(created.tenant_id);
    } catch (err) {
      console.error("Failed to register tenant:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 8000 });
    } finally {
      setIsSubmittingTenant(false);
    }
  };

  const checkTenantContactEmailUnique = (email: string) => {
    if (!(email || "").trim()) {
      setTenantFormErrors((prev) => {
        const next = { ...prev };
        delete next.email;
        return next;
      });
      return;
    }
    const emailError = validateTenantContactEmail(email, knownTenantEmails, knownUserEmails);
    setTenantFormErrors((prev) => {
      const next = { ...prev };
      if (emailError) next.email = emailError;
      else delete next.email;
      return next;
    });
  };

  // ----- Add tenant user -----
  const getDefaultUserTenantId = () => {
    const fromMe = user?.tenant_id?.trim();
    if (fromMe) return fromMe;
    return tenants[0]?.tenant_id ?? "";
  };

  const buildDefaultUserForm = (tenantId?: string): TenantUserFormState => ({
    tenant_id: tenantId ?? getDefaultUserTenantId(),
    email: "",
    username: "",
    full_name: "",
    phone_number: "",
    role: DEFAULT_TENANT_USER_ROLE,
  });

  const openUserModal = () => {
    setLockedUserFormTenantId(null);
    setUserForm(buildDefaultUserForm());
    setUserFormErrors({});
    setIsUserModalOpen(true);
    void refreshKnownAccountEmails();
  };

  const setUserFormTenantId = (tenant_id: string) => {
    setUserForm((prev) => ({ ...prev, tenant_id }));
  };

  const closeUserModal = () => {
    setLockedUserFormTenantId(null);
    setUserForm(buildDefaultUserForm());
    setUserFormErrors({});
    setIsUserModalOpen(false);
  };

  const checkUserEmailUnique = (email: string) => {
    if (!(email || "").trim()) {
      setUserFormErrors((prev) => {
        const next = { ...prev };
        delete next.email;
        return next;
      });
      return;
    }
    const emailError = validateTenantUserEmail(email, knownTenantEmails, knownUserEmails);
    setUserFormErrors((prev) => {
      const next = { ...prev };
      if (emailError) next.email = emailError;
      else delete next.email;
      return next;
    });
  };

  const resolveUserFormTenantId = () =>
    lockedUserFormTenantId ?? userForm.tenant_id?.trim() ?? "";

  const getLockedUserFormTenantLabel = (): string => {
    const tenantId = lockedUserFormTenantId;
    if (!tenantId) return "";
    const t =
      tenantDetailView?.tenant_id === tenantId
        ? tenantDetailView
        : tenants.find((row) => row.tenant_id === tenantId);
    return t?.organisation?.trim() || tenantId;
  };

  const handleRegisterUser = async () => {
    const tenantId = resolveUserFormTenantId();
    const errors: Record<string, string> = {};
    if (!tenantId) errors.tenant_id = "Tenant is required.";
    if (!userForm.full_name.trim()) errors.full_name = "Full name is required.";
    const emailError = validateTenantUserEmail(
      userForm.email,
      knownTenantEmails,
      knownUserEmails
    );
    if (emailError) errors.email = emailError;
    if (!userForm.username.trim() || userForm.username.trim().length < 3) {
      errors.username = "Username must be at least 3 characters.";
    }
    if (Object.keys(errors).length > 0) {
      setUserFormErrors(errors);
      toast({
        title: "Validation",
        description: Object.values(errors)[0],
        status: "error",
        isClosable: true,
      });
      return;
    }
    setUserFormErrors({});
    setIsSubmittingUser(true);
    try {
      await tenantService.registerUser({
        tenant_id: tenantId,
        email: userForm.email.trim(),
        username: userForm.username.trim(),
        full_name: userForm.full_name.trim() || undefined,
        phone_number: userForm.phone_number.trim() || undefined,
        role: userForm.role,
      });
      toast({
        title: "User added",
        description: `User ${userForm.username} provisioned under tenant.`,
        status: "success",
        duration: 4000,
        isClosable: true,
      });
      closeUserModal();
      await refreshTenantAndUserLists(tenantId);
    } catch (err) {
      console.error("Failed to register user:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 8000 });
    } finally {
      setIsSubmittingUser(false);
    }
  };

  const openAddUserForTenant = (tenant_id: string) => {
    setLockedUserFormTenantId(tenant_id);
    setUserForm(buildDefaultUserForm(tenant_id));
    setUserFormErrors({});
    setIsUserModalOpen(true);
    void refreshKnownAccountEmails();
  };

  const canSubmitTenantForm = useMemo(() => {
    if (isSubmittingTenant || isLoadingKnownEmails) return false;
    if (!tenantForm.organisation.trim() || !tenantForm.contact_name.trim()) return false;
    return !validateTenantContactEmail(tenantForm.email, knownTenantEmails, knownUserEmails);
  }, [
    isSubmittingTenant,
    isLoadingKnownEmails,
    tenantForm.organisation,
    tenantForm.contact_name,
    tenantForm.email,
    knownTenantEmails,
    knownUserEmails,
  ]);

  const canSubmitUserForm = useMemo(() => {
    if (isSubmittingUser || isLoadingKnownEmails) return false;
    const tenantId = lockedUserFormTenantId ?? userForm.tenant_id?.trim() ?? "";
    if (!tenantId || !userForm.full_name.trim()) return false;
    if (!userForm.username.trim() || userForm.username.trim().length < 3) return false;
    return !validateTenantUserEmail(userForm.email, knownTenantEmails, knownUserEmails);
  }, [
    isSubmittingUser,
    isLoadingKnownEmails,
    lockedUserFormTenantId,
    userForm.tenant_id,
    userForm.full_name,
    userForm.username,
    userForm.email,
    knownTenantEmails,
    knownUserEmails,
  ]);

  // ----- View tenant / view user -----
  const handleViewTenant = async (t: TenantView) => {
    setTenantDetailView(t);
    setTenantDetailSubTab("overview");
    try {
      const users = await loadTenantUsersForTenant(t.tenant_id);
      setTenantUsers(users);
      setKnownUserEmails(collectUserEmails(users));
    } catch (err) {
      console.error("Failed to fetch tenant users:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 6000 });
    }
  };

  const closeTenantDetailView = () => {
    setTenantDetailView(null);
    setTenantDetailSubTab("overview");
  };

  const handleViewUser = async (u: TenantUserView) => {
    setIsLoadingViewUser(true);
    setIsViewUserModalOpen(true);
    setViewUserDetail(null);
    try {
      const detail = await tenantService.getViewUser(u.user_id);
      setViewUserDetail(normalizeTenantUserRow(detail));
    } catch (err) {
      console.error("Failed to fetch user details:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsLoadingViewUser(false);
    }
  };

  const editTenantEmailExclusions = useMemo(
    () => ({
      excludeTenantEmail: editTenantRow?.email,
      excludeUserEmail: editTenantRow?.email,
    }),
    [editTenantRow?.email]
  );

  // ----- Edit tenant -----
  const handleOpenEditTenant = (t: TenantView) => {
    setEditTenantRow(t);
    setEditTenantForm({
      tenant_id: t.tenant_id,
      organisation: t.organisation,
      contact_name: t.contact_name,
      email: t.email,
      phone_number: t.phone_number ?? "",
    });
    setEditTenantFormErrors({});
    setIsEditTenantModalOpen(true);
    void refreshKnownAccountEmails();
  };

  const checkEditTenantContactEmailUnique = (email: string) => {
    if (!(email || "").trim()) {
      setEditTenantFormErrors((prev) => {
        const next = { ...prev };
        delete next.email;
        return next;
      });
      return;
    }
    const emailError = validateTenantContactEmail(
      email,
      knownTenantEmails,
      knownUserEmails,
      editTenantEmailExclusions
    );
    setEditTenantFormErrors((prev) => {
      const next = { ...prev };
      if (emailError) next.email = emailError;
      else delete next.email;
      return next;
    });
  };

  const handleSaveEditTenant = async () => {
    if (!editTenantForm.tenant_id) return;
    const errors: Record<string, string> = {};
    if (!editTenantForm.organisation?.trim()) {
      errors.organisation = "Organisation is required.";
    }
    const emailError = validateTenantContactEmail(
      editTenantForm.email ?? "",
      knownTenantEmails,
      knownUserEmails,
      editTenantEmailExclusions
    );
    if (emailError) errors.email = emailError;
    if (Object.keys(errors).length > 0) {
      setEditTenantFormErrors(errors);
      toast({
        title: "Validation",
        description: Object.values(errors)[0],
        status: "error",
        isClosable: true,
      });
      return;
    }
    setEditTenantFormErrors({});
    const emailChanged =
      normalizeEmail(editTenantForm.email ?? "") !==
      normalizeEmail(editTenantRow?.email ?? "");

    setIsSubmittingEditTenant(true);
    try {
      await tenantService.updateTenant({
        tenant_id: editTenantForm.tenant_id,
        organisation: editTenantForm.organisation,
        contact_name: editTenantForm.contact_name,
        email: editTenantForm.email,
        phone_number: editTenantForm.phone_number,
      });
      if (emailChanged) {
        toast({
          title: "Verification required",
          description:
            "A verification link was sent to the new contact email. The tenant contact email will update after it is verified.",
          status: "info",
          isClosable: true,
          duration: 8000,
        });
      } else {
        toast({ title: "Tenant updated", status: "success", isClosable: true, duration: 4000 });
      }
      setIsEditTenantModalOpen(false);
      setEditTenantRow(null);
      await refreshTenantAndUserLists(editTenantForm.tenant_id);
    } catch (err) {
      console.error("Failed to update tenant:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsSubmittingEditTenant(false);
    }
  };

  const closeEditTenantModal = () => {
    setIsEditTenantModalOpen(false);
    setEditTenantRow(null);
    setEditTenantFormErrors({});
  };

  const canSubmitEditTenantForm = useMemo(() => {
    if (isSubmittingEditTenant || isLoadingKnownEmails) return false;
    if (!editTenantForm.organisation?.trim()) return false;
    return !validateTenantContactEmail(
      editTenantForm.email ?? "",
      knownTenantEmails,
      knownUserEmails,
      editTenantEmailExclusions
    );
  }, [
    isSubmittingEditTenant,
    isLoadingKnownEmails,
    editTenantForm.organisation,
    editTenantForm.email,
    knownTenantEmails,
    knownUserEmails,
    editTenantEmailExclusions,
  ]);

  // ----- Status update -----
  const handleOpenTenantStatus = (t: TenantView, newStatus: TenantStatus) => {
    setStatusUpdateTarget({ type: "tenant", tenant_id: t.tenant_id, currentStatus: t.status });
    setStatusUpdateNewStatus(newStatus);
    setIsStatusDialogOpen(true);
  };

  const handleResendTenantSetupLink = async (t: TenantView) => {
    const email = t.email?.trim();
    if (!email) {
      toast({
        title: "Email required",
        description: "This tenant has no contact email to send a setup link.",
        status: "warning",
        isClosable: true,
        duration: 5000,
      });
      return;
    }
    setResendVerificationTenantId(t.tenant_id);
    try {
      const res = await authService.resendSetupLink({ email });
      toast({
        title: "Setup link sent",
        description:
          res?.message ??
          `If the account is not yet activated, a new setup link was sent to ${email}.`,
        status: "success",
        isClosable: true,
        duration: 8000,
      });
    } catch (err) {
      console.error("Failed to resend tenant setup link:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setResendVerificationTenantId(null);
    }
  };

  const handleOpenUserStatus = (u: TenantUserView, newStatus: TenantUserStatus) => {
    if (
      newStatus !== TENANT.USER_STATUS.ACTIVE &&
      newStatus !== TENANT.USER_STATUS.SUSPENDED
    ) {
      return;
    }
    const currentStatus = resolveTenantUserDisplayStatus(u);
    setStatusUpdateTarget({
      type: "user",
      tenant_id: tenantDetailView?.tenant_id ?? user?.tenant_id ?? "",
      user_id: u.user_id,
      currentStatus,
    });
    setStatusUpdateNewStatus(newStatus);
    setIsStatusDialogOpen(true);
  };

  const handleConfirmStatusUpdate = async () => {
    if (!statusUpdateTarget) return;
    setIsSubmittingStatus(true);
    try {
      if (statusUpdateTarget.type === "tenant") {
        await tenantService.updateTenantStatus({
          tenant_id: statusUpdateTarget.tenant_id,
          status: statusUpdateNewStatus as TenantStatus,
        });
        toast({ title: "Tenant status updated", status: "success", isClosable: true });
        await refreshTenantAndUserLists(statusUpdateTarget.tenant_id);
      } else {
        const isActive = statusUpdateNewStatus === TENANT.USER_STATUS.ACTIVE;
        await tenantService.updateUserStatus({
          tenant_id: statusUpdateTarget.tenant_id,
          user_id: statusUpdateTarget.user_id,
          is_active: isActive,
          is_tenant_active: isActive,
        });
        toast({ title: "User status updated", status: "success", isClosable: true });

        const ended = !isActive;
        const isCurrentTenantAdmin =
          ended &&
          userIdStr != null &&
          statusUpdateTarget.user_id === userIdStr &&
          (isTenantAdminRoleForSessionEnd(statusUpdateTarget.role) || isTenantAdmin);
        if (isCurrentTenantAdmin) {
          toast({
            title: "Signed out",
            description:
              "Your tenant admin account is no longer active. Sign in again when it is reactivated.",
            status: "warning",
            isClosable: true,
            duration: 6000,
          });
          forceFrontendSessionEnd();
          return;
        }
        await refreshTenantAndUserLists(statusUpdateTarget.tenant_id);
      }
      setIsStatusDialogOpen(false);
      setStatusUpdateTarget(null);
    } catch (err) {
      console.error("Failed to update status:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsSubmittingStatus(false);
    }
  };

  const closeStatusDialog = () => {
    if (!isSubmittingStatus) {
      setIsStatusDialogOpen(false);
      setStatusUpdateTarget(null);
    }
  };

  // ----- Edit tenant user -----
  const handleOpenEditUser = (u: TenantUserView) => {
    const normalizedRole = (u.role ?? u.roles?.[0] ?? "").trim().toUpperCase();
    const role =
      normalizedRole === "TENANT ADMIN" ? "TENANT ADMIN" : DEFAULT_TENANT_USER_ROLE;
    setEditUserRow(u);
    setEditUserForm({
      tenant_id: tenantDetailView?.tenant_id ?? user?.tenant_id ?? "",
      user_id: u.user_id,
      username: u.username ?? "",
      full_name: u.full_name ?? "",
      phone_number: u.phone_number ?? "",
      role,
    });
    setEditUserFormErrors({});
    setIsEditUserModalOpen(true);
  };

  const handleSaveEditUser = async () => {
    if (!editUserForm.tenant_id || !editUserForm.user_id) return;
    if (!editUserForm.username?.trim() || editUserForm.username.trim().length < 3) {
      toast({
        title: "Validation",
        description: "Username must be at least 3 characters.",
        status: "error",
        isClosable: true,
      });
      return;
    }
    setIsSubmittingEditUser(true);
    try {
      await tenantService.updateUser({
        tenant_id: editUserForm.tenant_id,
        user_id: editUserForm.user_id,
        username: editUserForm.username.trim(),
        full_name: editUserForm.full_name?.trim(),
        phone_number: editUserForm.phone_number?.trim(),
        role: editUserForm.role,
      });
      toast({ title: "User updated", status: "success", isClosable: true });
      setIsEditUserModalOpen(false);
      setEditUserRow(null);
      await refreshTenantAndUserLists(editUserForm.tenant_id);
    } catch (err) {
      console.error("Failed to update user:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsSubmittingEditUser(false);
    }
  };

  const closeEditUserModal = () => {
    setIsEditUserModalOpen(false);
    setEditUserRow(null);
    setEditUserFormErrors({});
  };

  // ----- Delete tenant user -----
  const handleOpenDeleteUser = (u: TenantUserView) => {
    setDeleteUserTarget({
      tenant_id: tenantDetailView?.tenant_id ?? user?.tenant_id ?? "",
      user_id: u.user_id,
      username: u.username ?? u.email,
    });
    setIsDeleteUserDialogOpen(true);
  };

  const handleConfirmDeleteUser = async () => {
    if (!deleteUserTarget) return;
    setIsDeletingUser(true);
    try {
      await tenantService.deleteUser({
        tenant_id: deleteUserTarget.tenant_id,
        user_id: deleteUserTarget.user_id,
      });
      toast({ title: "User deleted", status: "success", isClosable: true });
      setIsDeleteUserDialogOpen(false);
      setDeleteUserTarget(null);
      await refreshTenantAndUserLists(deleteUserTarget.tenant_id);
    } catch (err) {
      console.error("Failed to delete user:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsDeletingUser(false);
    }
  };

  const closeDeleteUserDialog = () => {
    if (!isDeletingUser) {
      setIsDeleteUserDialogOpen(false);
      setDeleteUserTarget(null);
    }
  };

  const closeViewUserModal = () => setIsViewUserModalOpen(false);

  return {
    // Data
    tenants,
    tenantUsers,
    filteredTenants,
    filteredTenantUsers,
    isLoadingTenants,
    isLoadingTenantUsers,
    // Filters
    tenantFilterStatus,
    setTenantFilterStatus,
    tenantSearch,
    setTenantSearch,
    userFilterStatus,
    setUserFilterStatus,
    userFilterRole,
    setUserFilterRole,
    userSearch,
    setUserSearch,
    handleResetTenantFilters,
    handleResetUserFilters,
    tenantUserRoleFilterOptions,
    isDefaultTenantUsersView,
    TENANT_ADMIN_UPDATABLE_STATUSES,
    // Create tenant
    isTenantModalOpen,
    tenantForm,
    setTenantForm,
    tenantFormErrors,
    setTenantFormErrors,
    isSubmittingTenant,
    openTenantModal,
    closeTenantModal,
    handleRegisterTenant,
    checkTenantContactEmailUnique,
    canSubmitTenantForm,
    isLoadingKnownEmails,
    // Add user
    isUserModalOpen,
    userForm,
    setUserForm,
    userFormErrors,
    setUserFormErrors,
    isSubmittingUser,
    openUserModal,
    closeUserModal,
    lockedUserFormTenantId,
    getLockedUserFormTenantLabel,
    setUserFormTenantId,
    handleRegisterUser,
    checkUserEmailUnique,
    canSubmitUserForm,
    openAddUserForTenant,
    // View user modal (tenant detail uses inline panel)
    viewUserDetail,
    isViewUserModalOpen,
    isLoadingViewUser,
    handleViewTenant,
    handleViewUser,
    closeViewUserModal,
    // Tenant detail sub-view
    tenantDetailView,
    tenantDetailSubTab,
    setTenantDetailSubTab,
    closeTenantDetailView,
    // Edit tenant
    isEditTenantModalOpen,
    editTenantRow,
    editTenantForm,
    setEditTenantForm,
    editTenantFormErrors,
    isSubmittingEditTenant,
    handleOpenEditTenant,
    handleSaveEditTenant,
    checkEditTenantContactEmailUnique,
    canSubmitEditTenantForm,
    closeEditTenantModal,
    // Status update
    statusUpdateTarget,
    statusUpdateNewStatus,
    isStatusDialogOpen,
    isSubmittingStatus,
    handleOpenTenantStatus,
    handleOpenUserStatus,
    handleConfirmStatusUpdate,
    closeStatusDialog,
    resendVerificationTenantId,
    handleResendTenantSetupLink,
    // Edit user
    isEditUserModalOpen,
    editUserRow,
    editUserForm,
    setEditUserForm,
    editUserFormErrors,
    setEditUserFormErrors,
    isSubmittingEditUser,
    handleOpenEditUser,
    handleSaveEditUser,
    closeEditUserModal,
    // Delete user
    deleteUserTarget,
    isDeleteUserDialogOpen,
    isDeletingUser,
    handleOpenDeleteUser,
    handleConfirmDeleteUser,
    closeDeleteUserDialog,
    // Fetch
    handleFetchTenants,
    handleFetchTenantUsers,
  };
}
