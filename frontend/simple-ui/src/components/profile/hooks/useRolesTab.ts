import { useMemo, useState } from "react";
import { showToast } from "../../../utils/toast";
import roleService, { Role } from "../../../services/roleService";
import type { User } from "../../../types/auth";
import {
  DEFAULT_TENANT_ASSIGNABLE_ROLES,
  formatDefaultTenantAssignableRoleLabel,
  isDefaultTenantAssignableRole,
} from "../../../utils/defaultTenant";
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

export function useRolesTab({ user, users, isLoadingUsers }: UseRolesTabOptions) {
  const [roles, setRoles] = useState<Role[]>([]);
  const [selectedUser, setSelectedUser] = useState<SelectedUserInfo | null>(null);
  const [selectedUserRoles, setSelectedUserRoles] = useState<string[]>([]);
  const [isLoadingRoles, setIsLoadingRoles] = useState(false);
  const [isLoadingUserRoles, setIsLoadingUserRoles] = useState(false);
  const [isManageRolesOpen, setIsManageRolesOpen] = useState(false);
  const [draftRole, setDraftRole] = useState<string>("");
  const [isSavingRoles, setIsSavingRoles] = useState(false);

  const isAdmin = Boolean(user?.roles?.includes("ADMIN"));
  const isModeratorOnly = Boolean(
    user?.roles?.includes("MODERATOR") && !user?.roles?.includes("ADMIN")
  );

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

  const saveManageRoles = async () => {
    if (!selectedUser) return;
    if (!isAdmin || isModeratorOnly) return;
    if (!draftRole) {
      showToast({
        type: "warning",
        message: "Select a role to assign to this user.",
      });
      return;
    }
    if (!isDefaultTenantAssignableRole(draftRole)) {
      showToast({
        type: "warning",
        message: `Only ${DEFAULT_TENANT_ASSIGNABLE_ROLES.map(
          formatDefaultTenantAssignableRoleLabel,
        ).join(", ")} can be assigned from Role Assignment.`,
      });
      return;
    }
    const originalPrimary = selectedUserRoles[0] ?? "";
    const toRemove = selectedUserRoles.filter((role) => role !== draftRole);
    const toAdd =
      draftRole && draftRole !== originalPrimary ? [draftRole] : [];

    if (toAdd.length === 0 && toRemove.length === 0 && selectedUserRoles.length <= 1) {
      showToast({
        type: "info",
        message: "No role updates to save.",
      });
      closeManageRoles();
      return;
    }

    setIsSavingRoles(true);
    const failedOps: string[] = [];
    try {
      for (const roleName of toRemove) {
        try {
          await roleService.removeRole(selectedUser.user_id, roleName);
        } catch {
          failedOps.push(`remove:${roleName}`);
        }
      }
      for (const roleName of toAdd) {
        try {
          await roleService.assignRole(selectedUser.user_id, roleName);
        } catch {
          failedOps.push(`assign:${roleName}`);
        }
      }

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
