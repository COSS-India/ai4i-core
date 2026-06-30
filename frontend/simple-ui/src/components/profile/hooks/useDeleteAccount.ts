import { useCallback, useState } from "react";
import type { User } from "../../../types/auth";
import { deleteUser, getViewTenant, listUsers } from "../../../services/tenantService";
import authService from "../../../services/authService";
import { resetAuthInitPromise } from "../../../hooks/useAuth";
import { isTenantAdminUser, normalizeRole, userHasRole } from "../../../utils/rbac";
import { showError } from "../../../utils/errorHandler";

const AUTH_UPDATED_EVENT = "auth:updated";

export const ACCOUNT_DELETED_LOGIN_MESSAGE = "Your account has been deleted.";

function extractApiErrorMessage(err: unknown): string | undefined {
  if (err && typeof err === "object") {
    const errorObj = err as {
      message?: string;
      response?: { data?: { detail?: string | { message?: string; code?: string } } };
    };
    const detail = errorObj.response?.data?.detail;
    if (typeof detail === "object" && detail?.message) {
      return String(detail.message);
    }
    if (typeof detail === "string") return detail;
    if (errorObj.message) return errorObj.message;
  }
  return undefined;
}

export function useDeleteAccount(user: User | null) {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [soleAdminBlockMessage, setSoleAdminBlockMessage] = useState<string | null>(null);
  const [isCheckingEligibility, setIsCheckingEligibility] = useState(false);

  const closeModal = useCallback(() => {
    if (!isDeleting) {
      setIsModalOpen(false);
    }
  }, [isDeleting]);

  const dismissSoleAdminBlock = useCallback(() => {
    setSoleAdminBlockMessage(null);
  }, []);

  const endSessionAndRedirect = useCallback(async () => {
    try {
      await authService.logout();
    } catch {
      // Tokens may already be invalidated server-side after account deletion.
    }
    authService.clearAuthTokens();
    authService.clearStoredUser();
    resetAuthInitPromise();
    if (typeof globalThis.window !== "undefined") {
      globalThis.window.dispatchEvent(new CustomEvent(AUTH_UPDATED_EVENT));
      globalThis.window.location.assign("/auth?message=account-deleted");
    }
  }, []);

  const handleOpenDeleteModal = useCallback(async () => {
    if (!user?.tenant_id || !user.user_id) {
      showError(new Error("Unable to delete account: missing tenant or user information."));
      return;
    }

    setSoleAdminBlockMessage(null);

    if (isTenantAdminUser(user.roles)) {
      setIsCheckingEligibility(true);
      try {
        const [{ users }, tenant] = await Promise.all([
          listUsers(user.tenant_id),
          getViewTenant(user.tenant_id),
        ]);
        const activeTenantAdmins = users.filter(
          (u) =>
            u.is_active &&
            (normalizeRole(u.role) === "TENANT ADMIN" || userHasRole(u.roles, "TENANT ADMIN"))
        );
        if (activeTenantAdmins.length <= 1) {
          const tenantLabel = tenant.organisation || tenant.contact_name || "your organisation";
          setSoleAdminBlockMessage(
            `You are the only administrator for ${tenantLabel}. Please promote another user to Tenant Admin before deleting your account.`
          );
          return;
        }
      } catch (err) {
        console.error("Failed to verify tenant admin eligibility:", err);
        showError(err);
        return;
      } finally {
        setIsCheckingEligibility(false);
      }
    }

    setIsModalOpen(true);
  }, [user]);

  const handleConfirmDelete = useCallback(async () => {
    if (!user?.tenant_id || !user.user_id) return;

    setIsDeleting(true);
    try {
      await deleteUser({
        tenant_id: user.tenant_id,
        user_id: user.user_id,
      });
      setIsModalOpen(false);
      await endSessionAndRedirect();
    } catch (err) {
      console.error("Failed to delete account:", err);
      const apiMessage = extractApiErrorMessage(err);
      if (apiMessage) {
        setSoleAdminBlockMessage(apiMessage);
        setIsModalOpen(false);
      } else {
        showError(err);
      }
    } finally {
      setIsDeleting(false);
    }
  }, [user, endSessionAndRedirect]);

  return {
    isModalOpen,
    isDeleting,
    isCheckingEligibility,
    soleAdminBlockMessage,
    handleOpenDeleteModal,
    handleConfirmDelete,
    closeModal,
    dismissSoleAdminBlock,
  };
}
