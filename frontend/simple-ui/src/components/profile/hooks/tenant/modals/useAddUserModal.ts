import { useCallback, useMemo, useState } from "react";
import * as tenantService from "../../../../../services/tenantService";
import { extractErrorInfo } from "../../../../../utils/errorHandler";
import {
  setFieldError,
  validateE164Phone,
  validateFullName,
} from "../../../../../utils/tenantFormValidation";
import type { TenantView } from "../../../../../types/tenant";
import type { TenantUserFormState } from "../../../types";
import { DEFAULT_TENANT_USER_ROLE, type TenantManagementUser } from "../shared";
import { useEmailAvailabilityField } from "../../useEmailAvailabilityField";
import type { TenantEmailRegistryState, TenantModalBaseOptions } from "./types";
import { collectAddUserErrors, emailAvailabilityConfirmed } from "./tenantModalValidation";

export interface UseAddUserModalOptions extends TenantModalBaseOptions {
  user: TenantManagementUser | null;
  tenants: TenantView[];
  tenantDetailView: TenantView | null;
  emailRegistry: TenantEmailRegistryState;
}

export function useAddUserModal({
  user,
  toast,
  tenants,
  tenantDetailView,
  refreshLists,
  emailRegistry,
}: UseAddUserModalOptions) {
  const [isUserModalOpen, setIsUserModalOpen] = useState(false);
  const [userForm, setUserForm] = useState<TenantUserFormState>({
    tenant_id: "",
    email: "",
    full_name: "",
    phone_number: "",
    role: DEFAULT_TENANT_USER_ROLE,
  });
  const [isSubmittingUser, setIsSubmittingUser] = useState(false);
  const [userFormErrors, setUserFormErrors] = useState<Record<string, string>>({});
  const [lockedUserFormTenantId, setLockedUserFormTenantId] = useState<string | null>(null);

  const patchUserFormError = useCallback((field: string, error: string | undefined) => {
    setUserFormErrors((prev) => setFieldError(prev, field, error));
  }, []);

  const getAddUserEmailCheckOptions = useCallback(
    () => ({
      mode: "tenant_user" as const,
      tenantEmails: emailRegistry.knownTenantEmails,
      userEmails: emailRegistry.knownUserEmails,
    }),
    [emailRegistry.knownTenantEmails, emailRegistry.knownUserEmails],
  );

  const emailAvailability = useEmailAvailabilityField({
    enabled: isUserModalOpen,
    email: userForm.email,
    patchError: patchUserFormError,
    getCheckOptions: getAddUserEmailCheckOptions,
    recheckKey: isUserModalOpen ? emailRegistry.knownEmailRecheckKey : undefined,
  });

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
    emailAvailability.clear();
    setIsUserModalOpen(true);
    void emailRegistry.refreshKnownAccountEmails();
  };

  const closeUserModal = () => {
    setLockedUserFormTenantId(null);
    setUserForm(buildDefaultUserForm());
    setUserFormErrors({});
    emailAvailability.clear();
    setIsUserModalOpen(false);
  };

  const openAddUserForTenant = (tenant_id: string) => {
    setLockedUserFormTenantId(tenant_id);
    setUserForm(buildDefaultUserForm(tenant_id));
    setUserFormErrors({});
    emailAvailability.clear();
    setIsUserModalOpen(true);
    void emailRegistry.refreshKnownAccountEmails();
  };

  const getLockedUserFormTenantLabel = (): string => {
    const tenantId = lockedUserFormTenantId;
    if (!tenantId) return "";
    const t =
      tenantDetailView?.tenant_id === tenantId
        ? tenantDetailView
        : tenants.find((row) => row.tenant_id === tenantId);
    return t?.organisation?.trim() || tenantId;
  };

  const resolveUserFormTenantId = () => lockedUserFormTenantId ?? userForm.tenant_id?.trim() ?? "";

  const handleRegisterUser = async () => {
    const errors = collectAddUserErrors(
      userForm,
      lockedUserFormTenantId,
      emailRegistry.knownTenantEmails,
      emailRegistry.knownUserEmails,
    );
    delete errors.email;
    const emailOk = await emailAvailability.verifyNow();
    if (!emailOk) return;
    if (Object.keys(errors).length > 0) {
      setUserFormErrors(errors);
      return;
    }
    const tenantId = resolveUserFormTenantId();
    setUserFormErrors({});
    setIsSubmittingUser(true);
    try {
      await tenantService.registerUser({
        tenant_id: tenantId,
        email: userForm.email.trim(),
        full_name: userForm.full_name.trim() || undefined,
        phone_number: userForm.phone_number.trim() || undefined,
        role: userForm.role,
      });
      toast({
        title: "User added",
        description: "User provisioned under tenant. The username is auto-generated from email.",
        status: "success",
        duration: 4000,
        isClosable: true,
      });
      closeUserModal();
      await refreshLists(tenantId);
    } catch (err) {
      console.error("Failed to register user:", err);
      const { title, message } = extractErrorInfo(err);
      toast({ title, description: message, status: "error", isClosable: true, duration: 8000 });
    } finally {
      setIsSubmittingUser(false);
    }
  };

  const handleUserFullNameChange = (full_name: string) => {
    setUserForm((prev) => ({ ...prev, full_name }));
    patchUserFormError("full_name", validateFullName(full_name));
  };

  const handleUserEmailChange = (email: string) => {
    setUserForm((prev) => ({ ...prev, email }));
    emailAvailability.handleChange(email);
  };

  const handleUserPhoneChange = (phone_number: string) => {
    setUserForm((prev) => ({ ...prev, phone_number }));
    patchUserFormError("phone_number", validateE164Phone(phone_number));
  };

  const setUserFormTenantId = (tenant_id: string) => {
    setUserForm((prev) => ({ ...prev, tenant_id }));
  };

  const canSubmitUserForm = useMemo(() => {
    if (isSubmittingUser || emailRegistry.isLoadingKnownEmails) return false;
    if (emailAvailability.status === "checking") return false;
    if (
      userForm.email.trim() &&
      !emailAvailabilityConfirmed(userForm.email, emailAvailability.status)
    ) {
      return false;
    }
    return (
      Object.keys(
        collectAddUserErrors(
          userForm,
          lockedUserFormTenantId,
          emailRegistry.knownTenantEmails,
          emailRegistry.knownUserEmails,
        ),
      ).length === 0
    );
  }, [
    isSubmittingUser,
    emailRegistry.isLoadingKnownEmails,
    emailRegistry.knownTenantEmails,
    emailRegistry.knownUserEmails,
    emailAvailability.status,
    lockedUserFormTenantId,
    userForm.tenant_id,
    userForm.full_name,
    userForm.email,
    userForm.phone_number,
  ]);

  return {
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
    handleUserEmailChange,
    handleUserPhoneChange,
    userEmailStatus: emailAvailability.status,
    canSubmitUserForm,
    openAddUserForTenant,
  };
}
