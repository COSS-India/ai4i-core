// Tenant Management: state (model) + handlers (controller) for Multi Tenant tab

import { useState, useEffect, useRef, useMemo } from "react";
import { useToastWithDeduplication } from "../../../hooks/useToastWithDeduplication";
import * as multiTenantService from "../../../services/multiTenantService";
import { extractErrorInfo } from "../../../utils/errorHandler";
import type { TenantView, TenantUserView, ServiceView } from "../../../types/multiTenant";
import type {
  TenantSubView,
  TenantFormState,
  TenantUserFormState,
  EditTenantFormState,
  EditUserFormState,
  StatusUpdateTargetUnion,
  DeleteUserTarget,
} from "../types";

const TENANT_SUBSCRIPTION_OPTIONS = [
  { value: "tts", label: "TTS" },
  { value: "asr", label: "ASR" },
  { value: "nmt", label: "NMT" },
  { value: "llm", label: "LLM" },
  { value: "pipeline", label: "Pipeline" },
  { value: "ocr", label: "OCR" },
  { value: "ner", label: "NER" },
  { value: "transliteration", label: "Transliteration" },
  { value: "language_detection", label: "Language Detection" },
  { value: "speaker_diarization", label: "Speaker Diarization" },
  { value: "language_diarization", label: "Language Diarization" },
  { value: "audio_language_detection", label: "Audio Language Detection" },
  { value: "speech_to_speech_pipeline", label: "Speech-to-Speech Pipeline" },
];

export interface UseTenantManagementOptions {
  /** Current user from useAuth(); used to set initial sub-view (adopter vs tenant) */
  user: { id?: number; is_superuser?: boolean; is_tenant?: boolean } | null;
}

export function useTenantManagement(options: UseTenantManagementOptions) {
  const { user } = options;
  const toast = useToastWithDeduplication();

  // ----- Model (state) -----
  const [tenants, setTenants] = useState<TenantView[]>([]);
  const [tenantUsers, setTenantUsers] = useState<TenantUserView[]>([]);
  const [isLoadingTenants, setIsLoadingTenants] = useState(false);
  const [isLoadingTenantUsers, setIsLoadingTenantUsers] = useState(false);
  const [multiTenantSubView, setMultiTenantSubView] = useState<TenantSubView>("adopter");
  const hasSetInitialMultiTenantView = useRef(false);

  const [tenantFilterStatus, setTenantFilterStatus] = useState<string>("all");
  const [tenantFilterServices, setTenantFilterServices] = useState<string>("all");
  const [tenantSearch, setTenantSearch] = useState("");
  const [userFilterStatus, setUserFilterStatus] = useState<string>("all");
  const [userFilterServices, setUserFilterServices] = useState<string>("all");
  const [userFilterRole, setUserFilterRole] = useState<string>("all");
  const [userSearch, setUserSearch] = useState("");

  // Create New Tenant modal
  const [isTenantModalOpen, setIsTenantModalOpen] = useState(false);
  const [tenantModalStep, setTenantModalStep] = useState<1 | 2>(1);
  const [tenantForm, setTenantForm] = useState<TenantFormState>({
    organization_name: "",
    domain: "",
    contact_name: "",
    contact_email: "",
    contact_phone: "",
    description: "",
    requested_subscriptions: [],
  });
  const [isSubmittingTenant, setIsSubmittingTenant] = useState(false);

  // Add New User modal
  const [isUserModalOpen, setIsUserModalOpen] = useState(false);
  const [userForm, setUserForm] = useState<TenantUserFormState>({
    tenant_id: "",
    email: "",
    username: "",
    full_name: "",
    services: [],
    is_approved: false,
    role: "USER",
  });
  const [isSubmittingUser, setIsSubmittingUser] = useState(false);

  // View tenant / view user modals
  const [viewTenantDetail, setViewTenantDetail] = useState<TenantView | null>(null);
  const [viewUserDetail, setViewUserDetail] = useState<TenantUserView | null>(null);
  const [isViewTenantModalOpen, setIsViewTenantModalOpen] = useState(false);
  const [isViewUserModalOpen, setIsViewUserModalOpen] = useState(false);
  const [isLoadingViewTenant, setIsLoadingViewTenant] = useState(false);
  const [isLoadingViewUser, setIsLoadingViewUser] = useState(false);

  // Tenant detail sub-view (new tab with Overview / Users) — when set, show detail view instead of tenant list
  const [tenantDetailView, setTenantDetailView] = useState<TenantView | null>(null);
  const [tenantDetailSubTab, setTenantDetailSubTab] = useState<"overview" | "users">("overview");

  // Edit tenant modal
  const [isEditTenantModalOpen, setIsEditTenantModalOpen] = useState(false);
  const [editTenantRow, setEditTenantRow] = useState<TenantView | null>(null);
  const [editTenantForm, setEditTenantForm] = useState<EditTenantFormState>({ tenant_id: "" });
  const [isSubmittingEditTenant, setIsSubmittingEditTenant] = useState(false);

  // Status update confirmation
  const [statusUpdateTarget, setStatusUpdateTarget] = useState<StatusUpdateTargetUnion | null>(null);
  const [statusUpdateNewStatus, setStatusUpdateNewStatus] = useState<string>("");
  const [isStatusDialogOpen, setIsStatusDialogOpen] = useState(false);
  const [isSubmittingStatus, setIsSubmittingStatus] = useState(false);

  // Edit user modal
  const [isEditUserModalOpen, setIsEditUserModalOpen] = useState(false);
  const [editUserRow, setEditUserRow] = useState<TenantUserView | null>(null);
  const [editUserForm, setEditUserForm] = useState<EditUserFormState>({ tenant_id: "", user_id: 0, role: "USER" });
  const [isSubmittingEditUser, setIsSubmittingEditUser] = useState(false);

  // Delete user confirmation
  const [deleteUserTarget, setDeleteUserTarget] = useState<DeleteUserTarget | null>(null);
  const [isDeleteUserDialogOpen, setIsDeleteUserDialogOpen] = useState(false);
  const [isDeletingUser, setIsDeletingUser] = useState(false);

  // Manage Services modal (for existing tenant)
  const [isManageServicesModalOpen, setIsManageServicesModalOpen] = useState(false);
  const [manageServicesTenant, setManageServicesTenant] = useState<TenantView | null>(null);
  const [availableServices, setAvailableServices] = useState<ServiceView[]>([]);
  const [manageServicesSelected, setManageServicesSelected] = useState<string[]>([]);
  const [isLoadingServices, setIsLoadingServices] = useState(false);
  const [isSavingManageServices, setIsSavingManageServices] = useState(false);

  // Create Tenant: load services for Requested subscriptions
  const [availableServicesForCreate, setAvailableServicesForCreate] = useState<ServiceView[] | null>(null);
  const [isLoadingServicesForCreate, setIsLoadingServicesForCreate] = useState(false);

  // Manage User Services modal (per-user subscriptions)
  const [manageUserServicesUser, setManageUserServicesUser] = useState<TenantUserView | null>(null);
  const [isManageUserServicesModalOpen, setIsManageUserServicesModalOpen] = useState(false);
  const [manageUserServicesSelected, setManageUserServicesSelected] = useState<string[]>([]);
  const [availableServicesForUser, setAvailableServicesForUser] = useState<ServiceView[]>([]);
  const [isLoadingUserServices, setIsLoadingUserServices] = useState(false);
  const [isSavingManageUserServices, setIsSavingManageUserServices] = useState(false);

  // ----- Effect: default Adopter vs Tenant sub-view -----
  useEffect(() => {
    if (!user?.id) {
      hasSetInitialMultiTenantView.current = false;
      return;
    }
    if (hasSetInitialMultiTenantView.current) return;
    if (user.is_superuser) {
      setMultiTenantSubView("adopter");
      hasSetInitialMultiTenantView.current = true;
    } else if (user.is_tenant) {
      setMultiTenantSubView("tenant");
      hasSetInitialMultiTenantView.current = true;
    }
  }, [user?.id, user?.is_superuser, user?.is_tenant]);

  // ----- Derived (filtered lists) -----
  const filteredTenants = useMemo(
    () =>
      tenants.filter((t) => {
        if (tenantFilterStatus !== "all" && t.status !== tenantFilterStatus) return false;
        const search = tenantSearch.trim().toLowerCase();
        if (search && !t.organization_name?.toLowerCase().includes(search) && !t.tenant_id?.toLowerCase().includes(search)) return false;
        if (tenantFilterServices !== "all" && !(t.subscriptions || []).some((s) => s.toLowerCase().includes(tenantFilterServices.toLowerCase()))) return false;
        return true;
      }),
    [tenants, tenantFilterStatus, tenantFilterServices, tenantSearch]
  );

  const filteredTenantUsers = useMemo(
    () =>
      tenantUsers.filter((u) => {
        if (userFilterStatus !== "all" && u.status !== userFilterStatus) return false;
        if (userFilterRole !== "all" && (u.role ?? "") !== userFilterRole) return false;
        if (userFilterServices !== "all" && !(u.subscriptions || []).some((s) => s.toLowerCase().includes(userFilterServices.toLowerCase()))) return false;
        const search = userSearch.trim().toLowerCase();
        if (search && !u.username?.toLowerCase().includes(search) && !u.email?.toLowerCase().includes(search)) return false;
        return true;
      }),
    [tenantUsers, userFilterStatus, userFilterRole, userFilterServices, userSearch]
  );

  // ----- Controllers (handlers) -----
  const handleFetchTenants = async () => {
    setIsLoadingTenants(true);
    try {
      const res = await multiTenantService.listTenants();
      setTenants(res.tenants || []);
    } catch (err) {
      console.error("Failed to fetch tenants:", err);
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(err);
      toast({ title: errorTitle, description: errorMessage, status: "error", isClosable: true, duration: 8000 });
      setTenants([]);
    } finally {
      setIsLoadingTenants(false);
    }
  };

  const handleFetchTenantUsers = async () => {
    setIsLoadingTenantUsers(true);
    try {
      const res = await multiTenantService.listUsers();
      const list = Array.isArray(res) ? (res as TenantUserView[]) : (res?.users ?? []);
      setTenantUsers(list);
    } catch (err) {
      console.error("Failed to fetch tenant users:", err);
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(err);
      toast({ title: errorTitle, description: errorMessage, status: "error", isClosable: true, duration: 8000 });
      setTenantUsers([]);
    } finally {
      setIsLoadingTenantUsers(false);
    }
  };

  const handleResetMultiTenantFilters = () => {
    setTenantFilterStatus("all");
    setTenantFilterServices("all");
    setTenantSearch("");
    setUserFilterStatus("all");
    setUserFilterServices("all");
    setUserFilterRole("all");
    setUserSearch("");
  };

  const openTenantModal = () => {
    setTenantForm({
      organization_name: "",
      domain: "",
      contact_name: "",
      contact_email: "",
      contact_phone: "",
      description: "",
      requested_subscriptions: [],
    });
    setAvailableServicesForCreate(null);
    setTenantModalStep(1);
    setIsTenantModalOpen(true);
  };

  const closeTenantModal = () => {
    setIsTenantModalOpen(false);
    setTenantModalStep(1);
  };

  const handleTenantStepNext = () => {
    if (tenantModalStep === 1) setTenantModalStep(2);
  };

  const handleTenantStepBack = () => {
    if (tenantModalStep === 2) setTenantModalStep(1);
  };

  const handleRegisterTenant = async () => {
    if (!tenantForm.organization_name.trim() || !tenantForm.domain.trim() || !tenantForm.contact_email.trim()) {
      toast({ title: "Validation", description: "Organization name, domain, and contact email are required.", status: "error", isClosable: true });
      return;
    }
    setIsSubmittingTenant(true);
    try {
      await multiTenantService.registerTenant({
        organization_name: tenantForm.organization_name.trim(),
        domain: tenantForm.domain.trim(),
        contact_email: tenantForm.contact_email.trim(),
        requested_subscriptions: tenantForm.requested_subscriptions?.length ? tenantForm.requested_subscriptions : [],
      });
      toast({ title: "Tenant created", description: "Verification email will be sent to the contact email. Tenant remains pending until verified.", status: "success", duration: 5000, isClosable: true });
      closeTenantModal();
      handleFetchTenants();
    } catch (err) {
      console.error("Failed to register tenant:", err);
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(err);
      toast({ title: errorTitle, description: errorMessage, status: "error", isClosable: true, duration: 8000 });
    } finally {
      setIsSubmittingTenant(false);
    }
  };

  const openUserModal = () => {
    const defaultTenant = tenants[0];
    setUserForm({
      tenant_id: defaultTenant?.tenant_id ?? "",
      email: "",
      username: "",
      full_name: "",
      services: [],
      is_approved: false,
      role: "USER",
    });
    setIsUserModalOpen(true);
  };

  /** When tenant changes in Add User form, clear service selection (all unchecked). */
  const setUserFormTenantId = (tenant_id: string) => {
    setUserForm((prev) => ({
      ...prev,
      tenant_id,
      services: [],
    }));
  };

  const closeUserModal = () => {
    setIsUserModalOpen(false);
  };

  const handleRegisterUser = async () => {
    if (!userForm.tenant_id || !userForm.full_name?.trim() || !userForm.email.trim() || !userForm.username.trim()) {
      toast({ title: "Validation", description: "Tenant, full name, email, and username are required.", status: "error", isClosable: true });
      return;
    }
    if (userForm.username.trim().length < 3) {
      toast({ title: "Validation", description: "Username must be at least 3 characters.", status: "error", isClosable: true });
      return;
    }
    setIsSubmittingUser(true);
    try {
      const tenant = tenants.find((t) => t.tenant_id === userForm.tenant_id);
      const allowedServices = tenant?.subscriptions ?? [];
      const servicesToSend = userForm.services.filter((s) => allowedServices.includes(s));
      await multiTenantService.registerUser({
        tenant_id: userForm.tenant_id,
        email: userForm.email.trim(),
        username: userForm.username.trim(),
        full_name: userForm.full_name.trim() || undefined,
        services: servicesToSend,
        is_approved: userForm.is_approved,
        role: userForm.role || "USER",
      });
      toast({ title: "User added", description: "User " + userForm.username + " registered under tenant.", status: "success", duration: 4000, isClosable: true });
      closeUserModal();
      handleFetchTenantUsers();
    } catch (err) {
      console.error("Failed to register user:", err);
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(err);
      toast({ title: errorTitle, description: errorMessage, status: "error", isClosable: true, duration: 8000 });
    } finally {
      setIsSubmittingUser(false);
    }
  };

  /** Open tenant detail sub-view (Overview / Users tab). Fetches full tenant detail and all users for the Users tab. */
  const handleViewTenant = async (t: TenantView) => {
    setTenantDetailView(t);
    setTenantDetailSubTab("overview");
    setViewTenantDetail(null);
    setIsLoadingViewTenant(true);
    try {
      const [detail, usersRes] = await Promise.all([
        multiTenantService.getViewTenant(t.tenant_id),
        multiTenantService.listUsers(),
      ]);
      setViewTenantDetail(detail);
      // Support both { users: [...] } and raw array (e.g. from gateway)
      const usersList: TenantUserView[] = Array.isArray(usersRes) ? (usersRes as TenantUserView[]) : (usersRes?.users ?? []);
      setTenantUsers(usersList);
    } catch (err) {
      console.error("Failed to fetch tenant details:", err);
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(err);
      toast({ title: errorTitle, description: errorMessage, status: "error", isClosable: true, duration: 6000 });
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
      const detail = await multiTenantService.getViewUser(u.user_id);
      setViewUserDetail(detail);
    } catch (err) {
      console.error("Failed to fetch user details:", err);
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(err);
      toast({ title: errorTitle, description: errorMessage, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsLoadingViewUser(false);
    }
  };

  const handleOpenEditTenant = (t: TenantView) => {
    setEditTenantRow(t);
    setEditTenantForm({
      tenant_id: t.tenant_id,
      organization_name: t.organization_name,
      contact_email: t.email,
      domain: t.domain,
    });
    setIsEditTenantModalOpen(true);
  };

  const handleSaveEditTenant = async () => {
    if (!editTenantForm.tenant_id) return;
    if (!editTenantForm.organization_name?.trim() || !editTenantForm.contact_email?.trim() || !editTenantForm.domain?.trim()) {
      toast({ title: "Validation", description: "Organization name, contact email, and domain are required.", status: "error", isClosable: true });
      return;
    }
    setIsSubmittingEditTenant(true);
    try {
      await multiTenantService.updateTenant({
        tenant_id: editTenantForm.tenant_id,
        organization_name: editTenantForm.organization_name,
        contact_email: editTenantForm.contact_email,
        domain: editTenantForm.domain,
        requested_quotas: editTenantForm.requested_quotas,
        usage_quota: editTenantForm.usage_quota,
      });
      toast({ title: "Tenant updated", status: "success", isClosable: true, duration: 4000 });
      setIsEditTenantModalOpen(false);
      setEditTenantRow(null);
      handleFetchTenants();
    } catch (err) {
      console.error("Failed to update tenant:", err);
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(err);
      toast({ title: errorTitle, description: errorMessage, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsSubmittingEditTenant(false);
    }
  };

  const openAddUserForTenant = (tenant_id: string) => {
    const tenant = tenants.find((t) => t.tenant_id === tenant_id);
    const tenantSubs = tenant?.subscriptions ?? [];
    setUserForm((prev) => ({
      ...prev,
      tenant_id,
      services: tenantSubs.length > 0 ? tenantSubs.slice(0, 2) : [],
    }));
    setIsUserModalOpen(true);
  };

  const handleOpenTenantStatus = (t: TenantView, newStatus: "ACTIVE" | "SUSPENDED" | "DEACTIVATED") => {
    setStatusUpdateTarget({ type: "tenant", tenant_id: t.tenant_id, currentStatus: t.status });
    setStatusUpdateNewStatus(newStatus);
    setIsStatusDialogOpen(true);
  };

  const handleOpenUserStatus = (u: TenantUserView, newStatus: "ACTIVE" | "SUSPENDED" | "DEACTIVATED") => {
    setStatusUpdateTarget({ type: "user", tenant_id: u.tenant_id, user_id: u.user_id, currentStatus: u.status });
    setStatusUpdateNewStatus(newStatus);
    setIsStatusDialogOpen(true);
  };

  const handleConfirmStatusUpdate = async () => {
    if (!statusUpdateTarget) return;
    setIsSubmittingStatus(true);
    try {
      if (statusUpdateTarget.type === "tenant") {
        await multiTenantService.updateTenantStatus({
          tenant_id: statusUpdateTarget.tenant_id,
          status: statusUpdateNewStatus as "ACTIVE" | "SUSPENDED" | "DEACTIVATED",
        });
        toast({ title: "Tenant status updated", status: "success", isClosable: true });
        handleFetchTenants();
      } else {
        await multiTenantService.updateUserStatus({
          tenant_id: statusUpdateTarget.tenant_id,
          user_id: statusUpdateTarget.user_id,
          status: statusUpdateNewStatus as "ACTIVE" | "SUSPENDED" | "DEACTIVATED",
        });
        toast({ title: "User status updated", status: "success", isClosable: true });
        handleFetchTenantUsers();
      }
      setIsStatusDialogOpen(false);
      setStatusUpdateTarget(null);
    } catch (err) {
      console.error("Failed to update status:", err);
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(err);
      toast({ title: errorTitle, description: errorMessage, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsSubmittingStatus(false);
    }
  };

  const handleOpenEditUser = (u: TenantUserView) => {
    setEditUserRow(u);
    setEditUserForm({
      tenant_id: u.tenant_id,
      user_id: u.user_id,
      username: u.username ?? "",
      email: u.email ?? "",
      is_approved: (u as { is_approved?: boolean }).is_approved ?? false,
      role: u.role ?? "USER",
    });
    setIsEditUserModalOpen(true);
  };

  const handleSaveEditUser = async () => {
    if (!editUserForm.tenant_id || !editUserForm.user_id) return;
    if (!editUserForm.username?.trim() || editUserForm.username.trim().length < 3 || !editUserForm.email?.trim()) {
      toast({ title: "Validation", description: "Username (min 3 characters) and email are required.", status: "error", isClosable: true });
      return;
    }
    setIsSubmittingEditUser(true);
    try {
      await multiTenantService.updateUser({
        tenant_id: editUserForm.tenant_id,
        user_id: editUserForm.user_id,
        ...(editUserForm.username !== undefined && editUserForm.username.trim().length >= 3 && { username: editUserForm.username.trim() }),
        ...(editUserForm.email !== undefined && editUserForm.email.trim() !== "" && { email: editUserForm.email.trim() }),
        ...(editUserForm.is_approved !== undefined && { is_approved: editUserForm.is_approved }),
        ...(editUserForm.role !== undefined && editUserForm.role.trim() !== "" && { role: editUserForm.role.trim() }),
      });
      toast({ title: "User updated", status: "success", isClosable: true });
      setIsEditUserModalOpen(false);
      setEditUserRow(null);
      handleFetchTenantUsers();
    } catch (err) {
      console.error("Failed to update user:", err);
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(err);
      toast({ title: errorTitle, description: errorMessage, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsSubmittingEditUser(false);
    }
  };

  const handleOpenDeleteUser = (u: TenantUserView) => {
    setDeleteUserTarget({ tenant_id: u.tenant_id, user_id: u.user_id, username: u.username ?? u.email });
    setIsDeleteUserDialogOpen(true);
  };

  const handleConfirmDeleteUser = async () => {
    if (!deleteUserTarget) return;
    setIsDeletingUser(true);
    try {
      await multiTenantService.deleteUser({ tenant_id: deleteUserTarget.tenant_id, user_id: deleteUserTarget.user_id });
      toast({ title: "User deleted", status: "success", isClosable: true });
      setIsDeleteUserDialogOpen(false);
      setDeleteUserTarget(null);
      handleFetchTenantUsers();
    } catch (err) {
      console.error("Failed to delete user:", err);
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(err);
      toast({ title: errorTitle, description: errorMessage, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsDeletingUser(false);
    }
  };

  const closeViewTenantModal = () => setIsViewTenantModalOpen(false);
  const closeViewUserModal = () => setIsViewUserModalOpen(false);
  const closeEditTenantModal = () => {
    setIsEditTenantModalOpen(false);
    setEditTenantRow(null);
  };
  const closeEditUserModal = () => {
    setIsEditUserModalOpen(false);
    setEditUserRow(null);
  };
  const closeStatusDialog = () => {
    if (!isSubmittingStatus) {
      setIsStatusDialogOpen(false);
      setStatusUpdateTarget(null);
    }
  };
  const closeDeleteUserDialog = () => {
    if (!isDeletingUser) {
      setIsDeleteUserDialogOpen(false);
      setDeleteUserTarget(null);
    }
  };

  // ----- Send Verification Email -----
  const [sendingVerificationTenantId, setSendingVerificationTenantId] = useState<string | null>(null);

  /** Validate email format */
  const isValidEmail = (email: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

  /** Send verification email to a PENDING tenant. Validates email first. */
  const handleSendVerificationEmail = async (tenantId: string, email: string | undefined) => {
    if (!email || !isValidEmail(email)) {
      toast({ title: "Invalid Email", description: "Cannot send verification email. The tenant's contact email is invalid or missing.", status: "error", isClosable: true, duration: 5000 });
      return;
    }
    setSendingVerificationTenantId(tenantId);
    try {
      await multiTenantService.sendVerificationEmail(tenantId);
      toast({ title: "Verification Email Sent", description: `Verification email sent to ${email}.`, status: "success", isClosable: true, duration: 5000 });
    } catch (err) {
      console.error("Failed to send verification email:", err);
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(err);
      toast({ title: errorTitle, description: errorMessage, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setSendingVerificationTenantId(null);
    }
  };

  // ----- Manage Services -----
  const openManageServices = (t: TenantView) => {
    setManageServicesTenant(t);
    setManageServicesSelected(t.subscriptions || []);
    setAvailableServices([]);
    setIsManageServicesModalOpen(true);
  };

  const closeManageServices = () => {
    if (!isSavingManageServices) {
      setIsManageServicesModalOpen(false);
      setManageServicesTenant(null);
      setAvailableServices([]);
    }
  };

  const loadServicesForManage = async () => {
    setIsLoadingServices(true);
    try {
      const res = await multiTenantService.listServices();
      setAvailableServices(res.services || []);
      toast({ title: "Services loaded", description: (res.services?.length ?? 0) + " service(s) available", status: "success", duration: 2000, isClosable: true });
    } catch (err) {
      console.error("Failed to load services:", err);
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(err);
      toast({ title: errorTitle, description: errorMessage, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsLoadingServices(false);
    }
  };

  /** Called on check: add subscription API. Called on uncheck: remove subscription API. */
  const handleTenantServiceCheckChange = async (serviceName: string, checked: boolean) => {
    if (!manageServicesTenant) return;
    setIsSavingManageServices(true);
    try {
      if (checked) {
        await multiTenantService.addTenantSubscriptions({
          tenant_id: manageServicesTenant.tenant_id,
          subscriptions: [serviceName],
        });
        setManageServicesSelected((prev) => (prev.includes(serviceName) ? prev : [...prev, serviceName]));
        setManageServicesTenant((prev) =>
          prev ? { ...prev, subscriptions: [...(prev.subscriptions || []), serviceName] } : null
        );
      } else {
        await multiTenantService.removeTenantSubscriptions({
          tenant_id: manageServicesTenant.tenant_id,
          subscriptions: [serviceName],
        });
        setManageServicesSelected((prev) => prev.filter((s) => s !== serviceName));
        setManageServicesTenant((prev) =>
          prev ? { ...prev, subscriptions: (prev.subscriptions || []).filter((s) => s !== serviceName) } : null
        );
      }
    } catch (err) {
      console.error("Failed to update tenant subscription:", err);
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(err);
      toast({ title: errorTitle, description: errorMessage, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsSavingManageServices(false);
    }
  };

  /** Save Changes for tenant Manage Services: front-end only (close + refetch), no API. */
  const saveManageServices = () => {
    closeManageServices();
    handleFetchTenants();
  };

  const loadServicesForCreateTenant = async () => {
    setIsLoadingServicesForCreate(true);
    try {
      const res = await multiTenantService.listServices();
      setAvailableServicesForCreate(res.services || []);
      toast({ title: "Services loaded", description: (res.services?.length ?? 0) + " service(s) available. Select requested subscriptions below.", status: "success", duration: 3000, isClosable: true });
    } catch (err) {
      console.error("Failed to load services:", err);
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(err);
      toast({ title: errorTitle, description: errorMessage, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsLoadingServicesForCreate(false);
    }
  };

  // ----- Manage User Services -----
  const openManageUserServices = (u: TenantUserView) => {
    setManageUserServicesUser(u);
    setManageUserServicesSelected(u.subscriptions || []);
    setAvailableServicesForUser([]);
    setIsManageUserServicesModalOpen(true);
  };

  const closeManageUserServices = () => {
    if (!isSavingManageUserServices) {
      setIsManageUserServicesModalOpen(false);
      setManageUserServicesUser(null);
      setAvailableServicesForUser([]);
    }
  };

  const loadServicesForUserManage = async () => {
    if (!manageUserServicesUser) return;
    setIsLoadingUserServices(true);
    try {
      // Get tenant subscriptions: from in-memory list or fetch tenant detail (e.g. when opened from Tenant Admin)
      let subscriptions: string[] = [];
      const tenantFromList = tenants.find((t) => t.tenant_id === manageUserServicesUser.tenant_id);
      if (tenantFromList?.subscriptions?.length) {
        subscriptions = tenantFromList.subscriptions;
      } else {
        try {
          const tenantDetail = await multiTenantService.getViewTenant(manageUserServicesUser.tenant_id);
          subscriptions = tenantDetail?.subscriptions ?? [];
        } catch (e) {
          console.warn("Could not load tenant detail for subscriptions:", e);
          toast({ title: "Tenant details unavailable", description: "Could not load tenant subscriptions. Try again or use Tenant Management to open Manage User Services.", status: "warning", duration: 5000, isClosable: true });
        }
      }
      const allottedLower = new Set(subscriptions.map((s) => String(s).toLowerCase()));
      const res = await multiTenantService.listServices();
      const allServices = res?.services ?? (Array.isArray(res) ? res : []);
      const tenantServicesOnly = allServices.filter((svc) =>
        allottedLower.has(String(svc.service_name ?? "").toLowerCase())
      );
      setAvailableServicesForUser(tenantServicesOnly);
      if (tenantServicesOnly.length === 0 && subscriptions.length === 0) {
        toast({ title: "No services", description: "This tenant has no allotted services. Add services via Manage Services for the tenant first.", status: "info", duration: 4000, isClosable: true });
      } else {
        toast({ title: "Services loaded", description: tenantServicesOnly.length + " service(s) allotted for this tenant", status: "success", duration: 2000, isClosable: true });
      }
    } catch (err) {
      console.error("Failed to load services:", err);
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(err);
      toast({ title: errorTitle, description: errorMessage, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsLoadingUserServices(false);
    }
  };

  /** Called on check: add user subscription API. Called on uncheck: remove user subscription API. */
  const handleUserServiceCheckChange = async (serviceName: string, checked: boolean) => {
    if (!manageUserServicesUser) return;
    setIsSavingManageUserServices(true);
    try {
      if (checked) {
        await multiTenantService.addUserSubscriptions({
          tenant_id: manageUserServicesUser.tenant_id,
          user_id: manageUserServicesUser.user_id,
          subscriptions: [serviceName],
        });
        setManageUserServicesSelected((prev) => (prev.includes(serviceName) ? prev : [...prev, serviceName]));
        setManageUserServicesUser((prev) =>
          prev ? { ...prev, subscriptions: [...(prev.subscriptions || []), serviceName] } : null
        );
      } else {
        await multiTenantService.removeUserSubscriptions({
          tenant_id: manageUserServicesUser.tenant_id,
          user_id: manageUserServicesUser.user_id,
          subscriptions: [serviceName],
        });
        setManageUserServicesSelected((prev) => prev.filter((s) => s !== serviceName));
        setManageUserServicesUser((prev) =>
          prev ? { ...prev, subscriptions: (prev.subscriptions || []).filter((s) => s !== serviceName) } : null
        );
      }
    } catch (err) {
      console.error("Failed to update user subscription:", err);
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(err);
      toast({ title: errorTitle, description: errorMessage, status: "error", isClosable: true, duration: 6000 });
    } finally {
      setIsSavingManageUserServices(false);
    }
  };

  /** Save Changes for user Manage Services: front-end only (close + refetch), no API. */
  const saveManageUserServices = () => {
    closeManageUserServices();
    handleFetchTenantUsers();
  };

  return {
    // Data
    tenants,
    tenantUsers,
    filteredTenants,
    filteredTenantUsers,
    multiTenantSubView,
    setMultiTenantSubView,
    isLoadingTenants,
    isLoadingTenantUsers,
    // Filters
    tenantFilterStatus,
    setTenantFilterStatus,
    tenantFilterServices,
    setTenantFilterServices,
    tenantSearch,
    setTenantSearch,
    userFilterStatus,
    setUserFilterStatus,
    userFilterServices,
    setUserFilterServices,
    userFilterRole,
    setUserFilterRole,
    userSearch,
    setUserSearch,
    handleResetMultiTenantFilters,
    // Create tenant
    isTenantModalOpen,
    tenantModalStep,
    tenantForm,
    setTenantForm,
    isSubmittingTenant,
    openTenantModal,
    closeTenantModal,
    handleTenantStepNext,
    handleTenantStepBack,
    handleRegisterTenant,
    TENANT_SUBSCRIPTION_OPTIONS,
    availableServicesForCreate,
    isLoadingServicesForCreate,
    loadServicesForCreateTenant,
    // Manage Services modal (tenant)
    isManageServicesModalOpen,
    manageServicesTenant,
    availableServices,
    manageServicesSelected,
    setManageServicesSelected,
    isLoadingServices,
    isSavingManageServices,
    openManageServices,
    closeManageServices,
    loadServicesForManage,
    saveManageServices,
    handleTenantServiceCheckChange,
    // Manage User Services modal
    manageUserServicesUser,
    isManageUserServicesModalOpen,
    manageUserServicesSelected,
    setManageUserServicesSelected,
    availableServicesForUser,
    isLoadingUserServices,
    isSavingManageUserServices,
    openManageUserServices,
    closeManageUserServices,
    loadServicesForUserManage,
    saveManageUserServices,
    handleUserServiceCheckChange,
    // Add user
    isUserModalOpen,
    userForm,
    setUserForm,
    isSubmittingUser,
    openUserModal,
    closeUserModal,
    setUserFormTenantId,
    handleRegisterUser,
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
    // Tenant detail sub-view (Overview / Users tab)
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
    // Send verification email
    sendingVerificationTenantId,
    handleSendVerificationEmail,
    // Fetch
    handleFetchTenants,
    handleFetchTenantUsers,
  };
}
