// Tenant Management state + handlers, backed by auth-service /api/v1/tenants/*.

import { useState, useEffect, useRef, useMemo } from "react";
import { forceFrontendSessionEnd } from "../../../hooks/useAuth";
import { useToastWithDeduplication } from "../../../hooks/useToastWithDeduplication";
import * as tenantService from "../../../services/tenantService";
import { extractErrorInfo } from "../../../utils/errorHandler";
import type { TenantStatus, TenantView, TenantUserView } from "../../../types/tenant";
import type {
  TenantSubView,
  TenantFormState,
  TenantUserFormState,
  EditTenantFormState,
  EditUserFormState,
  StatusUpdateTargetUnion,
  DeleteUserTarget,
} from "../types";

/** Tenant lifecycle status — values mirror the auth-service enum. */
const TENANT_STATUS_VALUES: TenantStatus[] = ["activated", "deactivated", "suspended"];

function isValidEmailFormat(email: string): boolean {
  const trimmed = (email || "").trim();
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed);
}

function isTenantAdminRoleForSessionEnd(role?: string): boolean {
  return (role ?? "").trim().toUpperCase() === "TENANT ADMIN";
}

export interface UseTenantManagementOptions {
  user: {
    id?: number | string;
    is_superuser?: boolean;
    is_tenant?: boolean;
    tenant_id?: string | null;
    roles?: string[];
  } | null;
}

export function useTenantManagement(options: UseTenantManagementOptions) {
  const { user } = options;
  const toast = useToastWithDeduplication();
  const isTenantAdmin = Boolean(user?.roles?.some((role) => isTenantAdminRoleForSessionEnd(role)));
  const isTenantScopedUser = Boolean((user?.is_tenant || isTenantAdmin) && !user?.is_superuser);
  const userIdStr = user?.id != null ? String(user.id) : null;

  // ----- State -----
  const [tenants, setTenants] = useState<TenantView[]>([]);
  const [tenantUsers, setTenantUsers] = useState<TenantUserView[]>([]);
  const [isLoadingTenants, setIsLoadingTenants] = useState(false);
  const [isLoadingTenantUsers, setIsLoadingTenantUsers] = useState(false);
  const [tenantSubView, setTenantSubView] = useState<TenantSubView>("adopter");
  const hasSetInitialTenantView = useRef(false);

  const [tenantFilterStatus, setTenantFilterStatus] = useState<string>("all");
  const [tenantSearch, setTenantSearch] = useState("");
  const [userFilterStatus, setUserFilterStatus] = useState<string>("all");
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

  // Add user modal
  const [isUserModalOpen, setIsUserModalOpen] = useState(false);
  const [userForm, setUserForm] = useState<TenantUserFormState>({
    tenant_id: "",
    email: "",
    username: "",
    full_name: "",
    phone_number: "",
  });
  const [isSubmittingUser, setIsSubmittingUser] = useState(false);
  const [userFormErrors, setUserFormErrors] = useState<Record<string, string>>({});

  // View modals
  const [viewTenantDetail, setViewTenantDetail] = useState<TenantView | null>(null);
  const [viewUserDetail, setViewUserDetail] = useState<TenantUserView | null>(null);
  const [isViewTenantModalOpen, setIsViewTenantModalOpen] = useState(false);
  const [isViewUserModalOpen, setIsViewUserModalOpen] = useState(false);
  const [isLoadingViewTenant, setIsLoadingViewTenant] = useState(false);
  const [isLoadingViewUser, setIsLoadingViewUser] = useState(false);

  // Tenant detail sub-view
  const [tenantDetailView, setTenantDetailView] = useState<TenantView | null>(null);
  const [tenantDetailSubTab, setTenantDetailSubTab] = useState<"overview" | "users">("overview");

  // Edit tenant modal
  const [isEditTenantModalOpen, setIsEditTenantModalOpen] = useState(false);
  const [editTenantRow, setEditTenantRow] = useState<TenantView | null>(null);
  const [editTenantForm, setEditTenantForm] = useState<EditTenantFormState>({ tenant_id: "" });
  const [isSubmittingEditTenant, setIsSubmittingEditTenant] = useState(false);

  // Status update confirmation
  const [statusUpdateTarget, setStatusUpdateTarget] = useState<StatusUpdateTargetUnion | null>(null);
  const [statusUpdateNewStatus, setStatusUpdateNewStatus] = useState<TenantStatus>("activated");
  const [isStatusDialogOpen, setIsStatusDialogOpen] = useState(false);
  const [isSubmittingStatus, setIsSubmittingStatus] = useState(false);

  // Edit user modal
  const [isEditUserModalOpen, setIsEditUserModalOpen] = useState(false);
  const [editUserRow, setEditUserRow] = useState<TenantUserView | null>(null);
  const [editUserForm, setEditUserForm] = useState<EditUserFormState>({ tenant_id: "", user_id: "" });
  const [editUserFormErrors, setEditUserFormErrors] = useState<Record<string, string>>({});
  const [isSubmittingEditUser, setIsSubmittingEditUser] = useState(false);

  // Delete user confirmation
  const [deleteUserTarget, setDeleteUserTarget] = useState<DeleteUserTarget | null>(null);
  const [isDeleteUserDialogOpen, setIsDeleteUserDialogOpen] = useState(false);
  const [isDeletingUser, setIsDeletingUser] = useState(false);

  // ----- Effects -----
  useEffect(() => {
    if (!user?.id) {
      hasSetInitialTenantView.current = false;
      return;
    }
    if (hasSetInitialTenantView.current) return;
    if (user.is_superuser) {
      setTenantSubView("adopter");
      hasSetInitialTenantView.current = true;
    } else if (isTenantScopedUser) {
      setTenantSubView("tenant");
      hasSetInitialTenantView.current = true;
    }
  }, [isTenantScopedUser, user?.id, user?.is_superuser]);

  // ----- Derived (filtered lists) -----
  const filteredTenants = useMemo(
    () =>
      tenants.filter((t) => {
        if (tenantFilterStatus !== "all" && t.status !== tenantFilterStatus) return false;
        const search = tenantSearch.trim().toLowerCase();
        if (
          search &&
          !t.organisation?.toLowerCase().includes(search) &&
          !t.tenant_id?.toLowerCase().includes(search)
        ) {
          return false;
        }
        return true;
      }),
    [tenants, tenantFilterStatus, tenantSearch]
  );

  const filteredTenantUsers = useMemo(
    () =>
      tenantUsers.filter((u) => {
        if (userFilterStatus !== "all") {
          const isActive = u.is_active && (u.is_tenant_active ?? true);
          const matches = userFilterStatus === "active" ? isActive : !isActive;
          if (!matches) return false;
        }
        const search = userSearch.trim().toLowerCase();
        if (
          search &&
          !u.username?.toLowerCase().includes(search) &&
          !u.email?.toLowerCase().includes(search)
        ) {
          return false;
        }
        return true;
      }),
    [tenantUsers, userFilterStatus, userSearch]
  );

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
      setTenants(res.tenants ?? []);
    } catch (err) {
      console.error("Failed to fetch tenants:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 8000 });
      setTenants([]);
    } finally {
      setIsLoadingTenants(false);
    }
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
      const res = await tenantService.listUsers(tenantId);
      setTenantUsers(res.users ?? []);
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
    if (user?.is_superuser) {
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
    setUserSearch("");
  };

  // ----- Create tenant -----
  const openTenantModal = () => {
    setTenantForm({ organisation: "", contact_name: "", email: "", phone_number: "" });
    setTenantFormErrors({});
    setIsTenantModalOpen(true);
  };

  const closeTenantModal = () => {
    setIsTenantModalOpen(false);
  };

  const handleRegisterTenant = async () => {
    const errors: Record<string, string> = {};
    if (!tenantForm.organisation.trim()) errors.organisation = "Organisation is required.";
    if (!tenantForm.contact_name.trim()) errors.contact_name = "Contact name is required.";
    if (!tenantForm.email.trim() || !isValidEmailFormat(tenantForm.email)) {
      errors.email = "Enter a valid email address.";
    }
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
        description: `${created.organisation} has been registered.`,
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
    const trimmed = (email || "").trim();
    const errors: Record<string, string> = {};
    if (trimmed && !isValidEmailFormat(trimmed)) {
      errors.email = "Enter a valid email address (e.g. name@example.com).";
    } else {
      const lower = trimmed.toLowerCase();
      if (lower && tenants.some((t) => (t.email ?? "").toLowerCase() === lower)) {
        errors.email = "This email is already registered with another tenant.";
      }
    }
    setTenantFormErrors(errors);
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
  });

  const openUserModal = () => {
    setUserForm(buildDefaultUserForm());
    setUserFormErrors({});
    setIsUserModalOpen(true);
  };

  const setUserFormTenantId = (tenant_id: string) => {
    setUserForm((prev) => ({ ...prev, tenant_id }));
  };

  const closeUserModal = () => {
    setUserForm(buildDefaultUserForm());
    setUserFormErrors({});
    setIsUserModalOpen(false);
  };

  const checkUserEmailUnique = (email: string) => {
    const trimmed = (email || "").trim();
    const errors: Record<string, string> = { ...userFormErrors };
    if (!trimmed) {
      delete errors.email;
      setUserFormErrors(errors);
      return;
    }
    if (!isValidEmailFormat(trimmed)) {
      errors.email = "Enter a valid email address (e.g. name@example.com).";
    } else if (
      tenantUsers.some((u) => (u.email ?? "").toLowerCase() === trimmed.toLowerCase())
    ) {
      errors.email = "This email is already registered with another user.";
    } else {
      delete errors.email;
    }
    setUserFormErrors(errors);
  };

  const handleRegisterUser = async () => {
    const errors: Record<string, string> = {};
    if (!userForm.tenant_id) errors.tenant_id = "Tenant is required.";
    if (!userForm.full_name.trim()) errors.full_name = "Full name is required.";
    if (!userForm.email.trim() || !isValidEmailFormat(userForm.email)) {
      errors.email = "Enter a valid email address.";
    }
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
        tenant_id: userForm.tenant_id,
        email: userForm.email.trim(),
        username: userForm.username.trim(),
        full_name: userForm.full_name.trim() || undefined,
        phone_number: userForm.phone_number.trim() || undefined,
      });
      toast({
        title: "User added",
        description: `User ${userForm.username} provisioned under tenant.`,
        status: "success",
        duration: 4000,
        isClosable: true,
      });
      closeUserModal();
      await refreshTenantAndUserLists(userForm.tenant_id);
    } catch (err) {
      console.error("Failed to register user:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 8000 });
    } finally {
      setIsSubmittingUser(false);
    }
  };

  const openAddUserForTenant = (tenant_id: string) => {
    setUserForm(buildDefaultUserForm(tenant_id));
    setUserFormErrors({});
    setIsUserModalOpen(true);
  };

  // ----- View tenant / view user -----
  const handleViewTenant = async (t: TenantView) => {
    setTenantDetailView(t);
    setTenantDetailSubTab("overview");
    setViewTenantDetail(null);
    setIsLoadingViewTenant(true);
    try {
      const [detail, usersRes] = await Promise.all([
        tenantService.getViewTenant(t.tenant_id),
        tenantService.listUsers(t.tenant_id),
      ]);
      setViewTenantDetail(detail);
      setTenantUsers(usersRes.users ?? []);
    } catch (err) {
      console.error("Failed to fetch tenant details:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsLoadingViewTenant(false);
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
      setViewUserDetail(detail);
    } catch (err) {
      console.error("Failed to fetch user details:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsLoadingViewUser(false);
    }
  };

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
    setIsEditTenantModalOpen(true);
  };

  const handleSaveEditTenant = async () => {
    if (!editTenantForm.tenant_id) return;
    if (!editTenantForm.organisation?.trim() || !editTenantForm.email?.trim()) {
      toast({
        title: "Validation",
        description: "Organisation and email are required.",
        status: "error",
        isClosable: true,
      });
      return;
    }
    setIsSubmittingEditTenant(true);
    try {
      await tenantService.updateTenant({
        tenant_id: editTenantForm.tenant_id,
        organisation: editTenantForm.organisation,
        contact_name: editTenantForm.contact_name,
        email: editTenantForm.email,
        phone_number: editTenantForm.phone_number,
      });
      toast({ title: "Tenant updated", status: "success", isClosable: true, duration: 4000 });
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
  };

  // ----- Status update -----
  const handleOpenTenantStatus = (t: TenantView, newStatus: TenantStatus) => {
    setStatusUpdateTarget({ type: "tenant", tenant_id: t.tenant_id, currentStatus: t.status });
    setStatusUpdateNewStatus(newStatus);
    setIsStatusDialogOpen(true);
  };

  const handleOpenUserStatus = (u: TenantUserView, newStatus: TenantStatus) => {
    const currentStatus = u.is_active && (u.is_tenant_active ?? true) ? "activated" : "deactivated";
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
          status: statusUpdateNewStatus,
        });
        toast({ title: "Tenant status updated", status: "success", isClosable: true });
        await refreshTenantAndUserLists(statusUpdateTarget.tenant_id);
      } else {
        const isActive = statusUpdateNewStatus === "activated";
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
    setEditUserRow(u);
    setEditUserForm({
      tenant_id: tenantDetailView?.tenant_id ?? user?.tenant_id ?? "",
      user_id: u.user_id,
      username: u.username ?? "",
      email: u.email ?? "",
      full_name: u.full_name ?? "",
      phone_number: u.phone_number ?? "",
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
        email: editUserForm.email?.trim(),
        full_name: editUserForm.full_name?.trim(),
        phone_number: editUserForm.phone_number?.trim(),
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

  const closeViewTenantModal = () => setIsViewTenantModalOpen(false);
  const closeViewUserModal = () => setIsViewUserModalOpen(false);

  return {
    // Data
    tenants,
    tenantUsers,
    filteredTenants,
    filteredTenantUsers,
    tenantSubView,
    setTenantSubView,
    isLoadingTenants,
    isLoadingTenantUsers,
    // Filters
    tenantFilterStatus,
    setTenantFilterStatus,
    tenantSearch,
    setTenantSearch,
    userFilterStatus,
    setUserFilterStatus,
    userSearch,
    setUserSearch,
    handleResetTenantFilters,
    TENANT_STATUS_VALUES,
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
    // Add user
    isUserModalOpen,
    userForm,
    setUserForm,
    userFormErrors,
    setUserFormErrors,
    isSubmittingUser,
    openUserModal,
    closeUserModal,
    setUserFormTenantId,
    handleRegisterUser,
    checkUserEmailUnique,
    openAddUserForTenant,
    // View tenant/user
    viewTenantDetail,
    viewUserDetail,
    isViewTenantModalOpen,
    isViewUserModalOpen,
    isLoadingViewTenant,
    isLoadingViewUser,
    handleViewTenant,
    handleViewUser,
    closeViewTenantModal,
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
    isSubmittingEditTenant,
    handleOpenEditTenant,
    handleSaveEditTenant,
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
