import { useCallback, useMemo, useState } from "react";
import * as tenantService from "../../../../../services/tenantService";
import { extractErrorInfo } from "../../../../../utils/errorHandler";
import {
  setFieldError,
  validateE164Phone,
  validateOptionalPersonName,
} from "../../../../../utils/tenantFormValidation";
import type { TenantUserView, TenantView } from "../../../../../types/tenant";
import type { EditUserFormState } from "../../../types";
import { normalizeTenantUserRow } from "../../../../../utils/tenantUserRoles";
import { DEFAULT_TENANT_USER_ROLE, type TenantManagementUser } from "../shared";
import type { TenantModalBaseOptions } from "./types";
import { collectEditUserErrors } from "./tenantModalValidation";

export interface UseEditUserModalOptions extends TenantModalBaseOptions {
  user: TenantManagementUser | null;
  tenantDetailView: TenantView | null;
}

export function useEditUserModal({
  user,
  toast,
  tenantDetailView,
  refreshLists,
}: UseEditUserModalOptions) {
  const [isEditUserModalOpen, setIsEditUserModalOpen] = useState(false);
  const [editUserRow, setEditUserRow] = useState<TenantUserView | null>(null);
  const [editUserForm, setEditUserForm] = useState<EditUserFormState>({
    tenant_id: "",
    user_id: "",
    role: DEFAULT_TENANT_USER_ROLE,
  });
  const [editUserFormErrors, setEditUserFormErrors] = useState<Record<string, string>>({});
  const [isSubmittingEditUser, setIsSubmittingEditUser] = useState(false);

  const patchEditUserFormError = useCallback((field: string, error: string | undefined) => {
    setEditUserFormErrors((prev) => setFieldError(prev, field, error));
  }, []);

  const handleOpenEditUser = (u: TenantUserView) => {
    const normalizedRole = (u.role ?? u.roles?.[0] ?? "").trim().toUpperCase();
    const role = normalizedRole === "TENANT ADMIN" ? "TENANT ADMIN" : DEFAULT_TENANT_USER_ROLE;
    setEditUserRow(normalizeTenantUserRow(u));
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
    const errors = collectEditUserErrors(editUserForm);
    if (Object.keys(errors).length > 0) {
      setEditUserFormErrors(errors);
      return;
    }
    setIsSubmittingEditUser(true);
    try {
      await tenantService.updateUser({
        tenant_id: editUserForm.tenant_id,
        user_id: editUserForm.user_id,
        username: (editUserForm.username ?? "").trim(),
        full_name: editUserForm.full_name?.trim(),
        phone_number: editUserForm.phone_number?.trim(),
        role: editUserForm.role,
      });
      toast({ title: "User updated", status: "success", isClosable: true });
      setIsEditUserModalOpen(false);
      setEditUserRow(null);
      await refreshLists(editUserForm.tenant_id);
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

  const handleEditUserUsernameChange = (username: string) => {
    setEditUserForm((prev) => ({ ...prev, username }));
    const trimmed = username.trim();
    patchEditUserFormError(
      "username",
      !trimmed || trimmed.length < 3 ? "Username must be at least 3 characters." : undefined,
    );
  };

  const handleEditUserFullNameChange = (full_name: string) => {
    setEditUserForm((prev) => ({ ...prev, full_name }));
    patchEditUserFormError("full_name", validateOptionalPersonName(full_name));
  };

  const handleEditUserPhoneChange = (phone_number: string) => {
    setEditUserForm((prev) => ({ ...prev, phone_number }));
    patchEditUserFormError("phone_number", validateE164Phone(phone_number));
  };

  const canSubmitEditUserForm = useMemo(() => {
    if (isSubmittingEditUser) return false;
    return Object.keys(collectEditUserErrors(editUserForm)).length === 0;
  }, [isSubmittingEditUser, editUserForm.username, editUserForm.full_name, editUserForm.phone_number]);

  return {
    isEditUserModalOpen,
    editUserRow,
    editUserForm,
    setEditUserForm,
    editUserFormErrors,
    setEditUserFormErrors,
    isSubmittingEditUser,
    handleOpenEditUser,
    handleSaveEditUser,
    handleEditUserUsernameChange,
    handleEditUserFullNameChange,
    handleEditUserPhoneChange,
    canSubmitEditUserForm,
    closeEditUserModal,
  };
}
