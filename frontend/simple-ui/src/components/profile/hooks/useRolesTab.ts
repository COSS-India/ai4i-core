import { useMemo, useState } from "react";
import { showToast } from "../../../utils/toast";
import roleService, { Role } from "../../../services/roleService";
import type { User } from "../../../types/auth";
import {
  DEFAULT_TENANT_ASSIGNABLE_ROLES,
  formatDefaultTenantAssignableRoleLabel,
  isDefaultTenantAssignableRole,
} from "../../../utils/defaultTenant";
import { isAdopterAdminUser, isPlatformAdminUser } from "../../../utils/rbac";
import {
  isSelfRegisteredUser,
  SELF_REGISTERED_ROLE_LOCKED_MESSAGE,
} from "../../../utils/registrationMethod";
import type { UserSearchablePick } from "../../common/UserSearchableSelect";

export interface UseRolesTabOptions {
  user: User | null;
  users: User[];
  isLoadingUsers: boolean;
}

export interface SelectedUserInfo {
  user_id: string;
  email: string;
  username: string;
}

/**
 * Removes then assigns roles one at a time so one failure does not abort the rest.
 * Returns the operations that failed.
 */
async function applyRoleChanges(
  userId: string,
  toRemove: string[],
  toAdd: string[],
): Promise<string[]> {
  const failedOps: string[] = [];
  for (const roleName of toRemove) {
    try {
      await roleService.removeRole(userId, roleName);
    } catch {
      failedOps.push(`remove:${roleName}`);
    }
  }
  for (const roleName of toAdd) {
    try {
      await roleService.assignRole(userId, roleName);
    } catch {
      failedOps.push(`assign:${roleName}`);
    }
  }
  return failedOps;
}

export function useRolesTab({ user, users, isLoadingUsers }: UseRolesTabOptions) {
  const [roles, setRoles] = useState<Role[]>([]);
  const [selectedUser, setSelectedUser] = useState<SelectedUserInfo | null>(null);
  const [selectedUserRoles, setSelectedUserRoles] = useState<string[]>([]);
  const [isLoadingRoles, setIsLoadingRoles] = useState(false);
  const [isLoadingUserRoles, setIsLoadingUserRoles] = useState(false);
  const [isManageRolesOpen, setIsManageRolesOpen] = useState(false);
  const [draftRole, setDraftRole] = useState<string>("");
  const [isSavingRoles, setIsSavingRoles] = useState(false);

  const isAdmin = isPlatformAdminUser(user?.roles);
  const isModeratorOnly = isAdopterAdminUser(user?.roles);

  const handleLoadRoles = async () => {
    setIsLoadingRoles(true);
    try {
      const allRoles = await roleService.listRoles();
      setRoles(allRoles);
      showToast({
        type: "success",
        message: `Loaded ${allRoles.length} roles`,
      });
    } catch (error) {
      showToast({
        type: "error",
        message: error instanceof Error ? error.message : "Failed to load roles",
      });
    } finally {
      setIsLoadingRoles(false);
    }
  };

  const handleUserSelect = async (userId: string | null, picked?: UserSearchablePick | null) => {
    if (userId == null) {
      setSelectedUser(null);
      setSelectedUserRoles([]);
      return;
    }
    const u = users.find((x) => x.user_id === userId) ?? picked;
    if (!u) return;
    setSelectedUser({ user_id: u.user_id, email: u.email, username: u.username || "" });
    setIsLoadingUserRoles(true);
    try {
      const userRolesData = await roleService.getUserRoles(u.user_id);
      setSelectedUserRoles(userRolesData.roles);
    } catch (error) {
      showToast({
        type: "error",
        message: error instanceof Error ? error.message : "Failed to load user roles",
      });
      setSelectedUserRoles([]);
    } finally {
      setIsLoadingUserRoles(false);
    }
  };

  /** Self-registered (email / Google) users are unvetted and must stay on USER. */
  const isSelectedUserSelfRegistered = useMemo(() => {
    if (!selectedUser) return false;
    const row = users.find((u) => u.user_id === selectedUser.user_id);
    return row != null && isSelfRegisteredUser(row);
  }, [selectedUser, users]);

  /** Adopter / Default tenant scope — see DEFAULT_TENANT_ASSIGNABLE_ROLES. */
  const availableRoles = useMemo(() => [...DEFAULT_TENANT_ASSIGNABLE_ROLES], []);

  const openManageRoles = async () => {
    if (!selectedUser) {
      showToast({
        type: "info",
        message: "Choose a user before managing roles.",
      });
      return;
    }
    if (!isAdmin || isModeratorOnly) return;
    if (isSelectedUserSelfRegistered) {
      showToast({ type: "info", message: SELF_REGISTERED_ROLE_LOCKED_MESSAGE });
      return;
    }
    if (selectedUserRoles.length > 1) {
      showToast({
        type: "info",
        message: "This user currently has multiple roles. Saving will normalize to one role.",
      });
    }
    setDraftRole("");
    setIsManageRolesOpen(true);
  };

  const closeManageRoles = () => {
    setIsManageRolesOpen(false);
    setDraftRole("");
  };

  const hasDraftChanges = (() => {
    if (!draftRole) return false;
    const originalPrimary = selectedUserRoles[0] ?? "";
    if (selectedUserRoles.length > 1) return true;
    return originalPrimary !== draftRole;
  })();

  /** Reason the draft role cannot be saved, or null when it can. */
  const getManageRolesBlockMessage = (): string | null => {
    if (isSelectedUserSelfRegistered) return SELF_REGISTERED_ROLE_LOCKED_MESSAGE;
    if (!draftRole) return "Select a role to assign to this user.";
    if (!isDefaultTenantAssignableRole(draftRole)) {
      return `Only ${DEFAULT_TENANT_ASSIGNABLE_ROLES.map(
        formatDefaultTenantAssignableRoleLabel,
      ).join(", ")} can be assigned from Role Assignment.`;
    }
    return null;
  };

  const saveManageRoles = async () => {
    if (!selectedUser) return;
    if (!isAdmin || isModeratorOnly) return;
    const blockMessage = getManageRolesBlockMessage();
    if (blockMessage) {
      showToast({ type: "warning", message: blockMessage });
      return;
    }
    const originalPrimary = selectedUserRoles[0] ?? "";
    const toRemove = selectedUserRoles.filter((role) => role !== draftRole);
    const toAdd = draftRole === originalPrimary ? [] : [draftRole];

    if (toAdd.length === 0 && toRemove.length === 0 && selectedUserRoles.length <= 1) {
      showToast({
        type: "info",
        message: "No role updates to save.",
      });
      closeManageRoles();
      return;
    }

    setIsSavingRoles(true);
    try {
      const failedOps = await applyRoleChanges(selectedUser.user_id, toRemove, toAdd);

      const refreshed = await roleService.getUserRoles(selectedUser.user_id);
      setSelectedUserRoles(refreshed.roles);

      if (failedOps.length === 0) {
        showToast({
          type: "success",
          message: `Updated roles for ${selectedUser.username}.`,
        });
      } else {
        showToast({
          type: "warning",
          message: `Some role changes failed (${failedOps.length}). Please retry.`,
        });
      }
      closeManageRoles();
    } catch (error) {
      showToast({
        type: "error",
        message: error instanceof Error ? error.message : "Failed to update roles",
      });
    } finally {
      setIsSavingRoles(false);
    }
  };

  return {
    roles,
    selectedUser,
    selectedUserRoles,
    isLoadingRoles,
    isLoadingUserRoles,
    isAdmin,
    isModeratorOnly,
    isSelectedUserSelfRegistered,
    isManageRolesOpen,
    draftRole,
    setDraftRole,
    isSavingRoles,
    hasDraftChanges,
    availableRoles,
    handleLoadRoles,
    handleUserSelect,
    openManageRoles,
    closeManageRoles,
    saveManageRoles,
  };
}
