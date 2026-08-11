// Tenant Management state + handlers, backed by auth-service tenant endpoints.

import { useState, useMemo, useCallback, useEffect } from "react";
import { forceFrontendSessionEnd } from "../../../hooks/useAuth";
import { showToast } from "../../../utils/toast";
import authService from "../../../services/authService";
import * as tenantService from "../../../services/tenantService";
import { showError } from "../../../utils/errorHandler";
import { refreshUntil } from "../../../utils/postMutationRefresh";
import {
  collectTenantContactEmails,
  collectUserEmails,
  normalizeEmail,
  validateEmailFormatOnly,
  validateTenantContactEmail,
  validateTenantUserEmail,
} from "../../../utils/tenantEmailValidation";
import { useEmailAvailabilityField } from "./useEmailAvailabilityField";
import {
  setFieldError,
  validateContactName,
  validateE164Phone,
  validateFullName,
  validateOptionalPersonName,
  validateOrganisation,
  validateOrganisationUnique,
} from "../../../utils/tenantFormValidation";
import {
  TENANT,
  TENANT_ADMIN_UPDATABLE_STATUSES,
  isTenantStatus,
  normalizeTenantStatus,
  resolveTenantUserDisplayStatus,
} from "../../../config/constants";
import type {
  TenantStatus,
  TenantUserStatus,
  TenantView,
  TenantUserView,
} from "../../../types/tenant";
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
  DEFAULT_ORG_USER_FORM_ROLE_OPTIONS,
  DEFAULT_TENANT_PLATFORM_ROLE_FILTER_LIST,
  isDefaultOrgUserRole,
  isDefaultTenant,
  resolveDefaultOrgFormRole,
} from "../../../utils/defaultTenant";
import {
  enrichDefaultOrgTenantUser,
  syncDefaultOrgUserRole,
} from "../../../utils/defaultOrgUserRoles";
import type { TenantAssignableRole } from "../../../types/tenant";
import type { TenantUserFormRole } from "../types";
import {
  applyTenantPendingSoftDeleteFlags,
  isPendingSoftDeletedTenant,
  markPendingSoftDeletedTenant,
} from "../../../utils/tenantPendingSoftDelete";

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
  const isTenantAdmin = Boolean(
    user?.roles?.some((role) => isTenantAdminRoleForSessionEnd(role)),
  );
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
  const [tenantFormErrors, setTenantFormErrors] = useState<
    Record<string, string>
  >({});
  const [isSubmittingTenant, setIsSubmittingTenant] = useState(false);
  const [knownTenantEmails, setKnownTenantEmails] = useState<Set<string>>(
    () => new Set(),
  );
  const [knownUserEmails, setKnownUserEmails] = useState<Set<string>>(
    () => new Set(),
  );
  const [isLoadingKnownEmails, setIsLoadingKnownEmails] = useState(false);

  // Add user modal
  const [isUserModalOpen, setIsUserModalOpen] = useState(false);
  const [userForm, setUserForm] = useState<TenantUserFormState>({
    tenant_id: "",
    email: "",
    full_name: "",
    phone_number: "",
    role: DEFAULT_TENANT_USER_ROLE,
  });
  const [isSubmittingUser, setIsSubmittingUser] = useState(false);
  const [userFormErrors, setUserFormErrors] = useState<Record<string, string>>(
    {},
  );
  /** When set, Add User modal tenant is fixed to this tenant (e.g. tenant detail page). */
  const [lockedUserFormTenantId, setLockedUserFormTenantId] = useState<
    string | null
  >(null);

  // View user modal (tenant detail uses inline panel via tenantDetailView, not a modal)
  const [viewUserDetail, setViewUserDetail] = useState<TenantUserView | null>(
    null,
  );
  const [isViewUserModalOpen, setIsViewUserModalOpen] = useState(false);

  // Tenant detail sub-view
  const [tenantDetailView, setTenantDetailView] = useState<TenantView | null>(
    null,
  );
  const [tenantDetailSubTab, setTenantDetailSubTab] = useState<
    "overview" | "users"
  >("overview");

  // Edit tenant modal
  const [isEditTenantModalOpen, setIsEditTenantModalOpen] = useState(false);
  const [editTenantRow, setEditTenantRow] = useState<TenantView | null>(null);
  const [editTenantForm, setEditTenantForm] = useState<EditTenantFormState>({
    tenant_id: "",
  });
  const [editTenantFormErrors, setEditTenantFormErrors] = useState<
    Record<string, string>
  >({});
  const [isSubmittingEditTenant, setIsSubmittingEditTenant] = useState(false);

  // Status update confirmation
  const [statusUpdateTarget, setStatusUpdateTarget] =
    useState<StatusUpdateTargetUnion | null>(null);
  const [statusUpdateNewStatus, setStatusUpdateNewStatus] = useState<
    TenantStatus | TenantUserStatus
  >(TENANT.STATUS.ACTIVE);
  const [isStatusDialogOpen, setIsStatusDialogOpen] = useState(false);
  const [isSubmittingStatus, setIsSubmittingStatus] = useState(false);

  const [resendVerificationTenantId, setResendVerificationTenantId] = useState<
    string | null
  >(null);

  const [resendVerificationUserId, setResendVerificationUserId] = useState<
    string | null
  >(null);

  // Edit user modal
  const [isEditUserModalOpen, setIsEditUserModalOpen] = useState(false);
  const [editUserRow, setEditUserRow] = useState<TenantUserView | null>(null);
  const [editUserForm, setEditUserForm] = useState<EditUserFormState>({
    tenant_id: "",
    user_id: "",
    role: DEFAULT_TENANT_USER_ROLE,
  });
  const [editUserFormErrors, setEditUserFormErrors] = useState<
    Record<string, string>
  >({});
  const [isSubmittingEditUser, setIsSubmittingEditUser] = useState(false);
  /** False when GET /roles/user failed — role field must not drive sync. */
  const [editUserRolesLoaded, setEditUserRolesLoaded] = useState(true);

  // Delete user confirmation
  const [deleteUserTarget, setDeleteUserTarget] =
    useState<DeleteUserTarget | null>(null);
  const [isDeleteUserDialogOpen, setIsDeleteUserDialogOpen] = useState(false);
  const [isDeletingUser, setIsDeletingUser] = useState(false);

  // ----- Derived (filtered lists) -----
  const filteredTenants = useMemo(
    () =>
      tenants.filter((t) => {
        if (
          tenantFilterStatus !== "all" &&
          normalizeTenantStatus(t.status) !==
            normalizeTenantStatus(tenantFilterStatus)
        ) {
          return false;
        }
        return tenantMatchesSearch(t, tenantSearch);
      }),
    [tenants, tenantFilterStatus, tenantSearch],
  );

  const activeUserListTenant = useMemo(() => {
    if (tenantDetailView) return tenantDetailView;
    if (isTenantScopedUser && user?.tenant_id) {
      return tenants.find((t) => t.tenant_id === user.tenant_id) ?? null;
    }
    return null;
  }, [tenantDetailView, isTenantScopedUser, user?.tenant_id, tenants]);

  const filteredTenantUsers = useMemo(
    () =>
      tenantUsers.filter((u) => {
        if (userFilterStatus !== "all") {
          const displayStatus = resolveTenantUserDisplayStatus(
            u,
            activeUserListTenant?.status,
          );
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
    [
      tenantUsers,
      userFilterStatus,
      userFilterRole,
      userSearch,
      activeUserListTenant?.status,
    ],
  );

  const isDefaultTenantUsersView = useMemo(
    () => activeUserListTenant != null && isDefaultTenant(activeUserListTenant),
    [activeUserListTenant],
  );

  const tenantUserRoleFilterOptions = useMemo(
    () =>
      isDefaultTenantUsersView
        ? DEFAULT_TENANT_PLATFORM_ROLE_FILTER_LIST
        : TENANT_USER_ROLE_FILTER_LIST,
    [isDefaultTenantUsersView],
  );

  useEffect(() => {
    setUserFilterRole("all");
  }, [activeUserListTenant?.tenant_id]);

  // ----- Fetchers -----
  /** Read tenants without committing React state (for refreshUntil polls). */
  const loadTenants = async (): Promise<TenantView[]> => {
    if (isTenantScopedUser) {
      const tenantId = user?.tenant_id?.trim();
      if (!tenantId) return [];
      const tenant = await tenantService.getViewTenant(tenantId);
      return tenant ? applyTenantPendingSoftDeleteFlags([tenant]) : [];
    }
    const res = await tenantService.listTenants();
    return applyTenantPendingSoftDeleteFlags(res.tenants ?? []);
  };

  const commitTenants = (rows: TenantView[]) => {
    setTenants(rows);
    if (!isTenantScopedUser) {
      setKnownTenantEmails(collectTenantContactEmails(rows));
    }
  };

  const handleFetchTenants = async (): Promise<TenantView[]> => {
    setIsLoadingTenants(true);
    try {
      const rows = await loadTenants();
      commitTenants(rows);
      return rows;
    } catch (err) {
      console.error("Failed to fetch tenants:", err);
      showError(err);
      setTenants([]);
      return [];
    } finally {
      setIsLoadingTenants(false);
    }
  };

  const resolveTenantById = (tenantId: string): TenantView | null => {
    if (tenantDetailView?.tenant_id === tenantId) return tenantDetailView;
    if (activeUserListTenant?.tenant_id === tenantId) return activeUserListTenant;
    return tenants.find((row) => row.tenant_id === tenantId) ?? null;
  };

  const patchTenantLocal = (tenantId: string, fields: Partial<TenantView>) => {
    setTenants((prev) =>
      prev.map((t) => (t.tenant_id === tenantId ? { ...t, ...fields } : t)),
    );
    setTenantDetailView((prev) =>
      prev?.tenant_id === tenantId ? { ...prev, ...fields } : prev,
    );
  };

  const loadTenantUsersForTenant = async (
    tenantId: string,
  ): Promise<TenantUserView[]> => {
    // Roles for default org are fetched lazily on view/edit (avoid N+1).
    const res = await tenantService.listUsers(tenantId);
    return normalizeTenantUserRoles(res.users ?? []);
  };

  const handleFetchTenantUsers = async (tenantIdOverride?: string) => {
    const tenantId =
      tenantIdOverride ??
      tenantDetailView?.tenant_id ??
      user?.tenant_id ??
      null;
    if (!tenantId) {
      showToast({
        type: "warning",
        message: "Unable to load users because no tenant ID is available.",
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
      showError(err);
      setTenantUsers([]);
    } finally {
      setIsLoadingTenantUsers(false);
    }
  };

  const refreshTenantAndUserLists = async (
    tenantIdOverride?: string,
    expectReady?: (rows: TenantView[]) => boolean,
  ) => {
    if (isAdmin) {
      if (expectReady) {
        const rows = await refreshUntil(loadTenants, expectReady);
        commitTenants(rows);
      } else {
        await handleFetchTenants();
      }
    }
    const tenantId =
      tenantIdOverride ??
      tenantDetailView?.tenant_id ??
      user?.tenant_id ??
      null;
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
    [],
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
        const batch = await authService.listUsersPage(
          offset,
          USER_EMAIL_PAGE_SIZE,
        );
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
  }, [
    isAdmin,
    user?.tenant_id,
    tenants,
    tenantUsers,
    syncKnownEmailsFromLists,
  ]);

  const patchTenantFormError = useCallback(
    (field: string, error: string | undefined) => {
      setTenantFormErrors((prev) => setFieldError(prev, field, error));
    },
    [],
  );

  const patchUserFormError = useCallback(
    (field: string, error: string | undefined) => {
      setUserFormErrors((prev) => setFieldError(prev, field, error));
    },
    [],
  );

  const patchEditTenantFormError = useCallback(
    (field: string, error: string | undefined) => {
      setEditTenantFormErrors((prev) => setFieldError(prev, field, error));
    },
    [],
  );

  const patchEditUserFormError = useCallback(
    (field: string, error: string | undefined) => {
      setEditUserFormErrors((prev) => setFieldError(prev, field, error));
    },
    [],
  );

  const knownEmailRecheckKey = isLoadingKnownEmails
    ? "loading"
    : `${knownTenantEmails.size}:${knownUserEmails.size}`;

  const getCreateTenantEmailCheckOptions = useCallback(
    () => ({
      mode: "tenant_contact" as const,
      tenantEmails: knownTenantEmails,
      userEmails: knownUserEmails,
    }),
    [knownTenantEmails, knownUserEmails],
  );

  const getAddUserEmailCheckOptions = useCallback(
    () => ({
      mode: "tenant_user" as const,
      tenantEmails: knownTenantEmails,
      userEmails: knownUserEmails,
    }),
    [knownTenantEmails, knownUserEmails],
  );

  const getEditTenantEmailCheckOptions = useCallback(() => {
    const current = editTenantForm.email ?? "";
    const unchanged =
      normalizeEmail(current) === normalizeEmail(editTenantRow?.email ?? "");
    return {
      mode: "tenant_contact" as const,
      tenantEmails: knownTenantEmails,
      userEmails: knownUserEmails,
      exclusions: {
        excludeTenantEmail: editTenantRow?.email,
        excludeUserEmail: editTenantRow?.email,
      },
      skipRemoteCheck: unchanged,
    };
  }, [
    knownTenantEmails,
    knownUserEmails,
    editTenantForm.email,
    editTenantRow?.email,
  ]);

  const createTenantEmailAvailability = useEmailAvailabilityField({
    enabled: isTenantModalOpen,
    email: tenantForm.email,
    patchError: patchTenantFormError,
    getCheckOptions: getCreateTenantEmailCheckOptions,
    recheckKey: isTenantModalOpen ? knownEmailRecheckKey : undefined,
  });

  const addUserEmailAvailability = useEmailAvailabilityField({
    enabled: isUserModalOpen,
    email: userForm.email,
    patchError: patchUserFormError,
    getCheckOptions: getAddUserEmailCheckOptions,
    recheckKey: isUserModalOpen ? knownEmailRecheckKey : undefined,
  });

  /** Contact email is editable only while the tenant is PENDING (pending verification). */
  const isEditTenantEmailEditable = useMemo(
    () => isTenantStatus(editTenantRow?.status, TENANT.STATUS.PENDING),
    [editTenantRow?.status],
  );

  const editTenantEmailAvailability = useEmailAvailabilityField({
    enabled: isEditTenantModalOpen && isEditTenantEmailEditable,
    email: editTenantForm.email ?? "",
    patchError: patchEditTenantFormError,
    getCheckOptions: getEditTenantEmailCheckOptions,
    recheckKey:
      isEditTenantModalOpen && isEditTenantEmailEditable
        ? knownEmailRecheckKey
        : undefined,
  });

  // ----- Create tenant -----
  const openTenantModal = () => {
    setTenantForm({
      organisation: "",
      contact_name: "",
      email: "",
      phone_number: "",
    });
    setTenantFormErrors({});
    createTenantEmailAvailability.clear();
    setIsTenantModalOpen(true);
    void refreshKnownAccountEmails();
  };

  const closeTenantModal = () => {
    createTenantEmailAvailability.clear();
    setIsTenantModalOpen(false);
  };

  const handleTenantOrganisationChange = (organisation: string) => {
    setTenantForm((prev) => ({ ...prev, organisation }));
    patchTenantFormError("organisation", validateOrganisation(organisation));
  };

  const handleTenantOrganisationBlur = (organisation: string) => {
    const formatError = validateOrganisation(organisation);
    if (formatError) {
      patchTenantFormError("organisation", formatError);
      return;
    }
    patchTenantFormError(
      "organisation",
      validateOrganisationUnique(organisation, tenants),
    );
  };

  const handleTenantContactNameChange = (contact_name: string) => {
    setTenantForm((prev) => ({ ...prev, contact_name }));
    patchTenantFormError("contact_name", validateContactName(contact_name));
  };

  const handleTenantContactNameBlur = (contact_name: string) => {
    patchTenantFormError("contact_name", validateContactName(contact_name));
  };

  const handleTenantEmailChange = (email: string) => {
    setTenantForm((prev) => ({ ...prev, email }));
    createTenantEmailAvailability.handleChange(email);
  };

  const handleTenantPhoneChange = (phone_number: string) => {
    setTenantForm((prev) => ({ ...prev, phone_number }));
    patchTenantFormError("phone_number", validateE164Phone(phone_number));
  };

  const handleUserFullNameChange = (full_name: string) => {
    setUserForm((prev) => ({ ...prev, full_name }));
    patchUserFormError("full_name", validateFullName(full_name));
  };

  const handleUserFullNameBlur = (full_name: string) => {
    patchUserFormError("full_name", validateFullName(full_name));
  };

  const handleUserEmailChange = (email: string) => {
    setUserForm((prev) => ({ ...prev, email }));
    addUserEmailAvailability.handleChange(email);
  };

  const handleTenantEmailBlur = () => {
    void createTenantEmailAvailability.verifyNow();
  };

  const handleUserEmailBlur = () => {
    void addUserEmailAvailability.verifyNow();
  };

  const handleUserPhoneChange = (phone_number: string) => {
    setUserForm((prev) => ({ ...prev, phone_number }));
    patchUserFormError("phone_number", validateE164Phone(phone_number));
  };

  const handleEditTenantOrganisationChange = (organisation: string) => {
    setEditTenantForm((prev) => ({ ...prev, organisation }));
    patchEditTenantFormError(
      "organisation",
      validateOrganisation(organisation),
    );
  };

  const handleEditTenantOrganisationBlur = (organisation: string) => {
    const formatError = validateOrganisation(organisation);
    if (formatError) {
      patchEditTenantFormError("organisation", formatError);
      return;
    }
    patchEditTenantFormError(
      "organisation",
      validateOrganisationUnique(
        organisation,
        tenants,
        editTenantForm.tenant_id,
      ),
    );
  };

  const handleEditTenantContactNameChange = (contact_name: string) => {
    setEditTenantForm((prev) => ({ ...prev, contact_name }));
    patchEditTenantFormError(
      "contact_name",
      validateOptionalPersonName(contact_name),
    );
  };

  const handleEditTenantEmailChange = (email: string) => {
    setEditTenantForm((prev) => ({ ...prev, email }));
    editTenantEmailAvailability.handleChange(email);
  };

  const handleEditTenantPhoneChange = (phone_number: string) => {
    setEditTenantForm((prev) => ({ ...prev, phone_number }));
    patchEditTenantFormError("phone_number", validateE164Phone(phone_number));
  };

  const handleEditUserFullNameChange = (full_name: string) => {
    setEditUserForm((prev) => ({ ...prev, full_name }));
    patchEditUserFormError("full_name", validateOptionalPersonName(full_name));
  };

  const handleEditUserPhoneChange = (phone_number: string) => {
    setEditUserForm((prev) => ({ ...prev, phone_number }));
    patchEditUserFormError("phone_number", validateE164Phone(phone_number));
  };

  const collectCreateTenantErrors = (): Record<string, string> => {
    const errors: Record<string, string> = {};
    const orgError = validateOrganisation(tenantForm.organisation);
    if (orgError) errors.organisation = orgError;
    else {
      const dupError = validateOrganisationUnique(
        tenantForm.organisation,
        tenants,
      );
      if (dupError) errors.organisation = dupError;
    }
    const contactError = validateContactName(tenantForm.contact_name);
    if (contactError) errors.contact_name = contactError;
    const emailError = validateTenantContactEmail(
      tenantForm.email,
      knownTenantEmails,
      knownUserEmails,
    );
    if (emailError) errors.email = emailError;
    const phoneError = validateE164Phone(tenantForm.phone_number);
    if (phoneError) errors.phone_number = phoneError;
    return errors;
  };

  const collectAddUserErrors = (): Record<string, string> => {
    const errors: Record<string, string> = {};
    const tenantId = lockedUserFormTenantId ?? userForm.tenant_id?.trim() ?? "";
    if (!tenantId) errors.tenant_id = "Tenant is required.";
    const fullNameError = validateFullName(userForm.full_name);
    if (fullNameError) errors.full_name = fullNameError;
    const emailError = validateTenantUserEmail(
      userForm.email,
      knownTenantEmails,
      knownUserEmails,
    );
    if (emailError) errors.email = emailError;
    const phoneError = validateE164Phone(userForm.phone_number);
    if (phoneError) errors.phone_number = phoneError;
    return errors;
  };

  const collectEditTenantErrors = (): Record<string, string> => {
    const errors: Record<string, string> = {};
    const orgError = validateOrganisation(editTenantForm.organisation ?? "");
    if (orgError) errors.organisation = orgError;
    else {
      const dupError = validateOrganisationUnique(
        editTenantForm.organisation ?? "",
        tenants,
        editTenantForm.tenant_id,
      );
      if (dupError) errors.organisation = dupError;
    }
    const contactError = validateOptionalPersonName(
      editTenantForm.contact_name ?? "",
    );
    if (contactError) errors.contact_name = contactError;
    if (isEditTenantEmailEditable) {
      const emailError = validateTenantContactEmail(
        editTenantForm.email ?? "",
        knownTenantEmails,
        knownUserEmails,
        {
          excludeTenantEmail: editTenantRow?.email,
          excludeUserEmail: editTenantRow?.email,
        },
      );
      if (emailError) errors.email = emailError;
    }
    const phoneError = validateE164Phone(editTenantForm.phone_number ?? "");
    if (phoneError) errors.phone_number = phoneError;
    return errors;
  };

  const collectEditUserErrors = (): Record<string, string> => {
    const errors: Record<string, string> = {};
    if (
      !editUserForm.username?.trim() ||
      editUserForm.username.trim().length < 3
    ) {
      errors.username = "Username must be at least 3 characters.";
    }
    const fullNameError = validateOptionalPersonName(
      editUserForm.full_name ?? "",
    );
    if (fullNameError) errors.full_name = fullNameError;
    const phoneError = validateE164Phone(editUserForm.phone_number ?? "");
    if (phoneError) errors.phone_number = phoneError;
    return errors;
  };

  const handleRegisterTenant = async () => {
    const errors = collectCreateTenantErrors();
    delete errors.email;
    const emailOk = await createTenantEmailAvailability.verifyNow();
    if (!emailOk) return;
    if (Object.keys(errors).length > 0) {
      setTenantFormErrors(errors);
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
      setTenants((prev) => {
        if (prev.some((t) => t.tenant_id === created.tenant_id)) return prev;
        return applyTenantPendingSoftDeleteFlags([created, ...prev]);
      });
      showToast({
        type: "success",
        message: `${created.organisation} is pending activation. The contact will receive a setup link by email.`,
      });
      closeTenantModal();
      await refreshTenantAndUserLists(
        created.tenant_id,
        (rows) => rows.some((t) => t.tenant_id === created.tenant_id),
      );
    } catch (err) {
      console.error("Failed to register tenant:", err);
      showError(err);
    } finally {
      setIsSubmittingTenant(false);
    }
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
    full_name: "",
    phone_number: "",
    role: DEFAULT_TENANT_USER_ROLE,
  });

  const openUserModal = () => {
    setLockedUserFormTenantId(null);
    setUserForm(buildDefaultUserForm());
    setUserFormErrors({});
    addUserEmailAvailability.clear();
    setIsUserModalOpen(true);
    void refreshKnownAccountEmails();
  };

  const setUserFormTenantId = (tenant_id: string) => {
    const selected = tenants.find((t) => t.tenant_id === tenant_id);
    setUserForm((prev) => {
      let nextRole: TenantUserFormRole = DEFAULT_TENANT_USER_ROLE;
      if (selected && isDefaultTenant(selected)) {
        nextRole = isDefaultOrgUserRole(prev.role)
          ? prev.role
          : DEFAULT_TENANT_USER_ROLE;
      } else if (prev.role === "TENANT ADMIN") {
        nextRole = "TENANT ADMIN";
      }
      return { ...prev, tenant_id, role: nextRole };
    });
  };

  const closeUserModal = () => {
    setLockedUserFormTenantId(null);
    setUserForm(buildDefaultUserForm());
    setUserFormErrors({});
    addUserEmailAvailability.clear();
    setIsUserModalOpen(false);
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
    const errors = collectAddUserErrors();
    delete errors.email;
    const emailOk = await addUserEmailAvailability.verifyNow();
    if (!emailOk) return;
    if (Object.keys(errors).length > 0) {
      setUserFormErrors(errors);
      return;
    }
    const tenantId = resolveUserFormTenantId();
    const tenant = resolveTenantById(tenantId);
    const isDefaultOrg = tenant != null && isDefaultTenant(tenant);
    if (isDefaultOrg && !isDefaultOrgUserRole(userForm.role)) {
      showToast({
        type: "warning",
        message: "Default Organisation users may only be User, Moderator, or Guest.",
      });
      return;
    }
    setUserFormErrors({});
    setIsSubmittingUser(true);
    try {
      // Tenant-user API only accepts USER | TENANT ADMIN. Default org is always
      // provisioned as USER, then role API sets Moderator/Guest when needed.
      const apiRole: TenantAssignableRole = isDefaultOrg
        ? DEFAULT_TENANT_USER_ROLE
        : userForm.role === "TENANT ADMIN"
          ? "TENANT ADMIN"
          : DEFAULT_TENANT_USER_ROLE;
      const created = await tenantService.registerUser({
        tenant_id: tenantId,
        email: userForm.email.trim(),
        full_name: userForm.full_name.trim() || undefined,
        phone_number: userForm.phone_number.trim() || undefined,
        role: apiRole,
      });
      if (isDefaultOrg && userForm.role !== DEFAULT_TENANT_USER_ROLE) {
        try {
          await syncDefaultOrgUserRole(created.user_id, userForm.role, [
            DEFAULT_TENANT_USER_ROLE,
          ]);
        } catch (syncErr) {
          console.error("Failed to apply default-org role after create:", syncErr);
          showToast({
            type: "warning",
            message:
              "User was created as User, but the selected role could not be applied. Edit the user to retry.",
          });
          closeUserModal();
          await refreshTenantAndUserLists(tenantId);
          return;
        }
      }
      showToast({
        type: "success",
        message:
          "User provisioned under tenant. The username is auto-generated from email.",
      });
      closeUserModal();
      await refreshTenantAndUserLists(tenantId);
    } catch (err) {
      console.error("Failed to register user:", err);
      showError(err);
    } finally {
      setIsSubmittingUser(false);
    }
  };

  const openAddUserForTenant = (tenant_id: string) => {
    setLockedUserFormTenantId(tenant_id);
    setUserForm(buildDefaultUserForm(tenant_id));
    setUserFormErrors({});
    addUserEmailAvailability.clear();
    setIsUserModalOpen(true);
    void refreshKnownAccountEmails();
  };

  const emailAvailabilityConfirmed = (
    email: string,
    status: typeof createTenantEmailAvailability.status,
  ) => {
    if (!email.trim()) return false;
    if (validateEmailFormatOnly(email)) return false;
    return status === "available";
  };

  const canSubmitTenantForm = useMemo(() => {
    if (isSubmittingTenant || isLoadingKnownEmails) return false;
    if (createTenantEmailAvailability.status === "checking") return false;
    if (
      tenantForm.email.trim() &&
      !emailAvailabilityConfirmed(
        tenantForm.email,
        createTenantEmailAvailability.status,
      )
    ) {
      return false;
    }
    return Object.keys(collectCreateTenantErrors()).length === 0;
  }, [
    isSubmittingTenant,
    isLoadingKnownEmails,
    createTenantEmailAvailability.status,
    tenantForm.organisation,
    tenantForm.contact_name,
    tenantForm.email,
    tenantForm.phone_number,
    knownTenantEmails,
    knownUserEmails,
    tenants,
  ]);

  const canSubmitUserForm = useMemo(() => {
    if (isSubmittingUser || isLoadingKnownEmails) return false;
    if (addUserEmailAvailability.status === "checking") return false;
    if (
      userForm.email.trim() &&
      !emailAvailabilityConfirmed(
        userForm.email,
        addUserEmailAvailability.status,
      )
    ) {
      return false;
    }
    return Object.keys(collectAddUserErrors()).length === 0;
  }, [
    isSubmittingUser,
    isLoadingKnownEmails,
    addUserEmailAvailability.status,
    lockedUserFormTenantId,
    userForm.tenant_id,
    userForm.full_name,
    userForm.email,
    userForm.phone_number,
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
      showError(err);
    }
  };

  const closeTenantDetailView = () => {
    setTenantDetailView(null);
    setTenantDetailSubTab("overview");
  };

  const handleViewUser = async (u: TenantUserView) => {
    let row = normalizeTenantUserRow(u);
    if (isDefaultTenantUsersView) {
      row = (await enrichDefaultOrgTenantUser(row)).user;
    }
    setViewUserDetail(row);
    setIsViewUserModalOpen(true);
  };

  // ----- Edit tenant -----
  const handleOpenEditTenant = async (t: TenantView) => {
    try {
      // Fetch unmasked PII for edit pre-fill only (list/view keep masked GETs).
      const unmasked = await tenantService.getViewTenant(t.tenant_id, {
        unmask: true,
      });
      setEditTenantRow(unmasked);
      setEditTenantForm({
        tenant_id: unmasked.tenant_id,
        organisation: unmasked.organisation,
        contact_name: unmasked.contact_name,
        email: unmasked.email,
        phone_number: unmasked.phone_number ?? "",
      });
      setEditTenantFormErrors({});
      editTenantEmailAvailability.clear();
      setIsEditTenantModalOpen(true);
      void refreshKnownAccountEmails();
    } catch (err) {
      console.error("Failed to load tenant for edit:", err);
      showError(err);
    }
  };

  const handleSaveEditTenant = async () => {
    if (!editTenantForm.tenant_id) return;
    const errors = collectEditTenantErrors();
    if (isEditTenantEmailEditable) {
      delete errors.email;
      const emailOk = await editTenantEmailAvailability.verifyNow();
      if (!emailOk) return;
    }
    if (Object.keys(errors).length > 0) {
      setEditTenantFormErrors(errors);
      return;
    }
    setEditTenantFormErrors({});
    const emailChanged =
      isEditTenantEmailEditable &&
      normalizeEmail(editTenantForm.email ?? "") !==
        normalizeEmail(editTenantRow?.email ?? "");

    setIsSubmittingEditTenant(true);
    try {
      const patch = {
        tenant_id: editTenantForm.tenant_id,
        organisation: editTenantForm.organisation,
        contact_name: editTenantForm.contact_name,
        phone_number: editTenantForm.phone_number,
        ...(isEditTenantEmailEditable
          ? { email: editTenantForm.email }
          : {}),
      };
      await tenantService.updateTenant(patch);

      patchTenantLocal(patch.tenant_id, {
        organisation: patch.organisation,
        contact_name: patch.contact_name,
        phone_number: patch.phone_number,
        ...(isEditTenantEmailEditable && !emailChanged
          ? { email: patch.email }
          : {}),
      });

      if (emailChanged) {
        showToast({
          type: "info",
          message:
            "A verification link was sent to the new contact email. The tenant contact email will update after it is verified.",
        });
      } else {
        showToast({ type: "success", message: "Tenant updated" });
      }
      setIsEditTenantModalOpen(false);
      setEditTenantRow(null);
      const expectedOrg = patch.organisation;
      const expectedContact = patch.contact_name;
      await refreshTenantAndUserLists(editTenantForm.tenant_id, (rows) =>
        rows.some(
          (t) =>
            t.tenant_id === editTenantForm.tenant_id &&
            t.organisation === expectedOrg &&
            t.contact_name === expectedContact,
        ),
      );
    } catch (err) {
      console.error("Failed to update tenant:", err);
      showError(err);
    } finally {
      setIsSubmittingEditTenant(false);
    }
  };

  const closeEditTenantModal = () => {
    editTenantEmailAvailability.clear();
    setIsEditTenantModalOpen(false);
    setEditTenantRow(null);
    setEditTenantFormErrors({});
  };

  const canSubmitEditTenantForm = useMemo(() => {
    if (isSubmittingEditTenant) return false;
    if (isEditTenantEmailEditable) {
      if (isLoadingKnownEmails) return false;
      if (editTenantEmailAvailability.status === "checking") return false;
      const email = editTenantForm.email ?? "";
      if (
        email.trim() &&
        !emailAvailabilityConfirmed(email, editTenantEmailAvailability.status)
      ) {
        return false;
      }
    }
    return Object.keys(collectEditTenantErrors()).length === 0;
  }, [
    isSubmittingEditTenant,
    isLoadingKnownEmails,
    isEditTenantEmailEditable,
    editTenantEmailAvailability.status,
    editTenantForm.organisation,
    editTenantForm.contact_name,
    editTenantForm.email,
    editTenantForm.phone_number,
    editTenantForm.tenant_id,
    editTenantRow?.email,
    knownTenantEmails,
    knownUserEmails,
    tenants,
  ]);

  const canSubmitEditUserForm = useMemo(() => {
    if (isSubmittingEditUser) return false;
    return Object.keys(collectEditUserErrors()).length === 0;
  }, [
    isSubmittingEditUser,
    editUserForm.username,
    editUserForm.full_name,
    editUserForm.phone_number,
  ]);

  // UI-only; server enforcement: AI4IDS-2750.
  const handleOpenTenantStatus = (t: TenantView, newStatus: TenantStatus) => {
    if (
      isDefaultTenant(t) &&
      (isTenantStatus(newStatus, TENANT.STATUS.SUSPENDED) ||
        isTenantStatus(newStatus, TENANT.STATUS.DEACTIVATED))
    ) {
      showToast({
        type: "warning",
        message: "The Default Organisation cannot be suspended or deactivated.",
      });
      return;
    }
    setStatusUpdateTarget({
      type: "tenant",
      tenant_id: t.tenant_id,
      currentStatus: t.status,
    });
    setStatusUpdateNewStatus(newStatus);
    setIsStatusDialogOpen(true);
  };

  const handleResendTenantVerificationEmail = async (t: TenantView) => {
    const email = t.email?.trim();
    if (!email) {
      showToast({
        type: "warning",
        message: "This tenant has no contact email to resend verification.",
      });
      return;
    }
    const tenantIdNum = Number(t.tenant_id);
    if (!Number.isFinite(tenantIdNum) || tenantIdNum < 1) {
      showToast({
        type: "warning",
        message: "This tenant has no valid tenant ID to resend the setup link.",
      });
      return;
    }
    setResendVerificationTenantId(t.tenant_id);
    try {
      const res = await authService.resendSetupLink(
        { email, tenant_id: tenantIdNum },
        { withAuth: true },
      );
      showToast({
        type: "success",
        message:
          res?.message ??
          `A new activation link was sent to ${email} if the account is not yet activated.`,
      });
    } catch (err) {
      console.error("Failed to resend tenant verification email:", err);
      showError(err);
    } finally {
      setResendVerificationTenantId(null);
    }
  };

  const handleResendTenantUserVerification = async (u: TenantUserView) => {
    const tenantId = tenantDetailView?.tenant_id ?? user?.tenant_id;
    if (!tenantId || !u.user_id) {
      showToast({
        type: "warning",
        message: "Missing tenant or user ID to resend the setup link.",
      });
      return;
    }
    try {
      setResendVerificationUserId(u.user_id);
      // Resolve by user_id (unmasked) — do not use masked email or
      // /auth/resend-verification (no-ops for passwordless tenant users).
      const res = await tenantService.resendTenantUserSetupLink(
        tenantId,
        u.user_id,
      );
      showToast({
        type: "success",
        message:
          res?.message ??
          "A password setup link has been sent to the user's email.",
      });
    } catch (err) {
      console.error("Failed to resend tenant user setup link:", err);
      showError(err);
    } finally {
      setResendVerificationUserId(null);
    }
  };

  const handleOpenUserStatus = (
    u: TenantUserView,
    newStatus: TenantUserStatus,
  ) => {
    if (
      newStatus !== TENANT.USER_STATUS.ACTIVE &&
      newStatus !== TENANT.USER_STATUS.SUSPENDED
    ) {
      return;
    }
    const currentStatus = resolveTenantUserDisplayStatus(
      u,
      activeUserListTenant?.status,
    );
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
        const wasPendingDeactivate =
          isTenantStatus(
            statusUpdateTarget.currentStatus,
            TENANT.STATUS.PENDING,
          ) && statusUpdateNewStatus === TENANT.STATUS.DEACTIVATED;
        await tenantService.updateTenantStatus({
          tenant_id: statusUpdateTarget.tenant_id,
          status: statusUpdateNewStatus as TenantStatus,
        });
        if (wasPendingDeactivate) {
          markPendingSoftDeletedTenant(statusUpdateTarget.tenant_id);
        }
        patchTenantLocal(statusUpdateTarget.tenant_id, {
          status: statusUpdateNewStatus as TenantStatus,
        });
        showToast({ type: "success", message: "Tenant status updated" });
        const expectedStatus = statusUpdateNewStatus as TenantStatus;
        const targetTenantId = statusUpdateTarget.tenant_id;
        await refreshTenantAndUserLists(targetTenantId, (rows) =>
          rows.some(
            (t) =>
              t.tenant_id === targetTenantId &&
              normalizeTenantStatus(t.status) ===
                normalizeTenantStatus(expectedStatus),
          ),
        );
      } else {
        const isActive = statusUpdateNewStatus === TENANT.USER_STATUS.ACTIVE;
        await tenantService.updateUserStatus({
          tenant_id: statusUpdateTarget.tenant_id,
          user_id: statusUpdateTarget.user_id,
          is_active: isActive,
          is_tenant_active: isActive,
        });
        showToast({ type: "success", message: "User status updated" });

        const ended = !isActive;
        const isCurrentTenantAdmin =
          ended &&
          userIdStr != null &&
          statusUpdateTarget.user_id === userIdStr &&
          (isTenantAdminRoleForSessionEnd(statusUpdateTarget.role) ||
            isTenantAdmin);
        if (isCurrentTenantAdmin) {
          showToast({
            type: "warning",
            message:
              "Your tenant admin account is no longer active. Sign in again when it is reactivated.",
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
      showError(err);
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
  const handleOpenEditUser = async (u: TenantUserView) => {
    const tenantId = tenantDetailView?.tenant_id ?? user?.tenant_id ?? "";
    if (!tenantId) {
      showToast({
        type: "error",
        message: "Tenant is required to edit user.",
      });
      return;
    }
    try {
      // No single-user GET; list with unmask to pre-fill editable phone.
      const { users } = await tenantService.listUsers(tenantId, {
        unmask: true,
      });
      const unmasked =
        users.find((row) => row.user_id === u.user_id) ?? null;
      if (!unmasked) {
        showToast({ type: "error", message: "User not found." });
        return;
      }
      const editingDefaultOrg =
        (activeUserListTenant != null && isDefaultTenant(activeUserListTenant)) ||
        (tenantDetailView != null && isDefaultTenant(tenantDetailView)) ||
        tenants.some(
          (row) => row.tenant_id === tenantId && isDefaultTenant(row),
        );

      let role: TenantUserFormRole = DEFAULT_TENANT_USER_ROLE;
      let editRow: TenantUserView = unmasked;
      let rolesLoaded = true;
      if (editingDefaultOrg) {
        const enriched = await enrichDefaultOrgTenantUser(unmasked);
        editRow = enriched.user;
        rolesLoaded = enriched.rolesLoaded;
        const resolved = resolveDefaultOrgFormRole(editRow.roles, editRow.role);
        role =
          isDefaultOrgUserRole(resolved) || resolved === "ADMIN"
            ? (resolved as TenantUserFormRole)
            : DEFAULT_TENANT_USER_ROLE;
        editRow = { ...editRow, role };
        if (!rolesLoaded) {
          showToast({
            type: "warning",
            message:
              "Could not load roles for this user. Role changes are disabled until reload.",
          });
        }
      } else {
        const normalizedRole = (
          unmasked.role ??
          unmasked.roles?.[0] ??
          ""
        )
          .trim()
          .toUpperCase();
        role =
          normalizedRole === "TENANT ADMIN"
            ? "TENANT ADMIN"
            : DEFAULT_TENANT_USER_ROLE;
      }
      setEditUserRow(editRow);
      setEditUserRolesLoaded(rolesLoaded);
      setEditUserForm({
        tenant_id: tenantId,
        user_id: unmasked.user_id,
        username: unmasked.username ?? "",
        full_name: unmasked.full_name ?? "",
        phone_number: unmasked.phone_number ?? "",
        role,
      });
      setEditUserFormErrors({});
      setIsEditUserModalOpen(true);
    } catch (err) {
      console.error("Failed to load user for edit:", err);
      showError(err);
    }
  };

  const handleEditUserUsernameChange = (username: string) => {
    setEditUserForm((prev) => ({ ...prev, username }));
    const trimmed = username.trim();
    patchEditUserFormError(
      "username",
      !trimmed || trimmed.length < 3
        ? "Username must be at least 3 characters."
        : undefined,
    );
  };

  const handleSaveEditUser = async () => {
    if (!editUserForm.tenant_id || !editUserForm.user_id) return;
    const errors = collectEditUserErrors();
    if (Object.keys(errors).length > 0) {
      setEditUserFormErrors(errors);
      return;
    }
    const tenant = resolveTenantById(editUserForm.tenant_id);
    const isDefaultOrg = tenant != null && isDefaultTenant(tenant);
    if (
      isDefaultOrg &&
      editUserForm.role !== "ADMIN" &&
      !isDefaultOrgUserRole(editUserForm.role)
    ) {
      showToast({
        type: "warning",
        message: "Default Organisation users may only be User, Moderator, or Guest.",
      });
      return;
    }
    setIsSubmittingEditUser(true);
    try {
      let didSyncDefaultOrgRole = false;
      let syncedDefaultOrgRole: string | null = null;
      if (isDefaultOrg) {
        await tenantService.updateUser({
          tenant_id: editUserForm.tenant_id,
          user_id: editUserForm.user_id,
          username: (editUserForm.username ?? "").trim(),
          full_name: editUserForm.full_name?.trim(),
          phone_number: editUserForm.phone_number?.trim(),
        });
        // Sync only when the operator changed the role and we trust the loaded roles.
        // Avoids silent demotion on profile-only edits after a failed roles fetch.
        const initialRole = (editUserRow?.role ?? "").trim().toUpperCase();
        const nextRole = editUserForm.role.trim().toUpperCase();
        if (isDefaultOrgUserRole(nextRole) && nextRole !== initialRole) {
          if (!editUserRolesLoaded) {
            showToast({
              type: "warning",
              message:
                "Role was not updated because current roles could not be loaded. Other changes were saved.",
            });
          } else {
            await syncDefaultOrgUserRole(
              editUserForm.user_id,
              nextRole,
              editUserRow?.roles,
            );
            didSyncDefaultOrgRole = true;
            syncedDefaultOrgRole = nextRole;
          }
        }
      } else {
        await tenantService.updateUser({
          tenant_id: editUserForm.tenant_id,
          user_id: editUserForm.user_id,
          username: (editUserForm.username ?? "").trim(),
          full_name: editUserForm.full_name?.trim(),
          phone_number: editUserForm.phone_number?.trim(),
          role:
            editUserForm.role === "TENANT ADMIN"
              ? "TENANT ADMIN"
              : DEFAULT_TENANT_USER_ROLE,
        });
      }
      showToast({ type: "success", message: "User updated" });
      setIsEditUserModalOpen(false);
      setEditUserRow(null);
      setEditUserRolesLoaded(true);
      // Default org role updates may be eventually consistent across endpoints.
      // Ensure the users list role column is updated to avoid stale UI state.
      if (didSyncDefaultOrgRole && syncedDefaultOrgRole) {
        const tenantId = editUserForm.tenant_id;
        const targetRole = syncedDefaultOrgRole;
        const finalUsers = await refreshUntil(
          () => loadTenantUsersForTenant(tenantId),
          (rows) =>
            rows.some(
              (row) =>
                row.user_id === editUserForm.user_id &&
                tenantUserHasRole(row, targetRole),
            ),
          6,
          500,
        );
        setTenantUsers(finalUsers);
        setKnownUserEmails(collectUserEmails(finalUsers));
        if (isAdmin) {
          await handleFetchTenants();
        }
      } else {
        await refreshTenantAndUserLists(editUserForm.tenant_id);
      }
    } catch (err) {
      console.error("Failed to update user:", err);
      showError(err);
    } finally {
      setIsSubmittingEditUser(false);
    }
  };

  const closeEditUserModal = () => {
    setIsEditUserModalOpen(false);
    setEditUserRow(null);
    setEditUserFormErrors({});
    setEditUserRolesLoaded(true);
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
      showToast({ type: "success", message: "User deleted" });
      setIsDeleteUserDialogOpen(false);
      setDeleteUserTarget(null);
      await refreshTenantAndUserLists(deleteUserTarget.tenant_id);
    } catch (err) {
      console.error("Failed to delete user:", err);
      showError(err);
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

  const closeViewUserModal = () => {
    setIsViewUserModalOpen(false);
    setViewUserDetail(null);
  };

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
    activeUserListTenant,
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
    handleTenantOrganisationChange,
    handleTenantOrganisationBlur,
    handleTenantContactNameChange,
    handleTenantContactNameBlur,
    handleTenantEmailChange,
    handleTenantEmailBlur,
    handleTenantPhoneChange,
    tenantEmailStatus: createTenantEmailAvailability.status,
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
    handleUserFullNameChange,
    handleUserFullNameBlur,
    handleUserEmailChange,
    handleUserEmailBlur,
    handleUserPhoneChange,
    userEmailStatus: addUserEmailAvailability.status,
    canSubmitUserForm,
    openAddUserForTenant,
    // View user modal (tenant detail uses inline panel)
    viewUserDetail,
    isViewUserModalOpen,
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
    handleEditTenantOrganisationChange,
    handleEditTenantOrganisationBlur,
    handleEditTenantContactNameChange,
    handleEditTenantEmailChange,
    handleEditTenantPhoneChange,
    isEditTenantEmailEditable,
    editTenantEmailStatus: editTenantEmailAvailability.status,
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
    resendVerificationUserId,
    handleResendTenantVerificationEmail,
    handleResendTenantUserVerification,
    isPendingSoftDeletedTenant,
    // Edit user
    isEditUserModalOpen,
    editUserRow,
    editUserForm,
    setEditUserForm,
    editUserFormErrors,
    setEditUserFormErrors,
    editUserRolesLoaded,
    isSubmittingEditUser,
    handleOpenEditUser,
    handleSaveEditUser,
    handleEditUserUsernameChange,
    handleEditUserFullNameChange,
    handleEditUserPhoneChange,
    canSubmitEditUserForm,
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
