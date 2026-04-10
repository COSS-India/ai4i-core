import { useState } from "react";
import { useToastWithDeduplication } from "../../../hooks/useToastWithDeduplication";
import roleService, { Role } from "../../../services/roleService";
import type { User } from "../../../types/auth";
import type { UserSearchablePick } from "../../common/UserSearchableSelect";

export interface UseRolesTabOptions {
  user: User | null;
  users: User[];
  isLoadingUsers: boolean;
}

export interface SelectedUserInfo {
  id: number;
  email: string;
  username: string;
}

export function useRolesTab({ user, users, isLoadingUsers }: UseRolesTabOptions) {
  const toast = useToastWithDeduplication();
  const [roles, setRoles] = useState<Role[]>([]);
  const [selectedUser, setSelectedUser] = useState<SelectedUserInfo | null>(null);
  const [selectedUserRoles, setSelectedUserRoles] = useState<string[]>([]);
  const [isLoadingRoles, setIsLoadingRoles] = useState(false);
  const [isLoadingUserRoles, setIsLoadingUserRoles] = useState(false);
  const [isManageRolesOpen, setIsManageRolesOpen] = useState(false);
  const [draftRole, setDraftRole] = useState<string>("");
  const [isSavingRoles, setIsSavingRoles] = useState(false);

  const isAdmin = Boolean(user?.roles?.includes("ADMIN") || user?.is_superuser);
  const isModeratorOnly = Boolean(
    user?.roles?.includes("MODERATOR") && !user?.roles?.includes("ADMIN") && !user?.is_superuser
  );

  const handleLoadRoles = async () => {
    setIsLoadingRoles(true);
    try {
      const allRoles = await roleService.listRoles();
      setRoles(allRoles);
      toast({
        title: "Roles Loaded",
        description: `Loaded ${allRoles.length} roles`,
        status: "success",
        duration: 2000,
        isClosable: true,
      });
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to load roles",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsLoadingRoles(false);
    }
  };

  const handleUserSelect = async (userId: number | null, picked?: UserSearchablePick | null) => {
    if (userId == null) {
      setSelectedUser(null);
      setSelectedUserRoles([]);
      return;
    }
    const u = users.find((x) => x.id === userId) ?? picked;
    if (!u) return;
    setSelectedUser({ id: u.id, email: u.email, username: u.username || "" });
    setIsLoadingUserRoles(true);
    try {
      const userRolesData = await roleService.getUserRoles(u.id);
      setSelectedUserRoles(userRolesData.roles);
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to load user roles",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      setSelectedUserRoles([]);
    } finally {
      setIsLoadingUserRoles(false);
    }
  };

  const availableRoles = roles
    .map((role) => role.name)
    .filter((name) => name && name.trim().length > 0)
    .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));

  const openManageRoles = async () => {
    if (!selectedUser) {
      toast({
        title: "Select user",
        description: "Choose a user before managing roles.",
        status: "info",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    if (!isAdmin || isModeratorOnly) return;
    if (roles.length === 0) {
      await handleLoadRoles();
    }
    const primaryRole = selectedUserRoles[0] ?? "";
    if (selectedUserRoles.length > 1) {
      toast({
        title: "Multiple roles detected",
        description: "This user currently has multiple roles. Saving will normalize to one role.",
        status: "info",
        duration: 4500,
        isClosable: true,
      });
    }
    setDraftRole(primaryRole);
    setIsManageRolesOpen(true);
  };

  const closeManageRoles = () => {
    setIsManageRolesOpen(false);
    setDraftRole("");
  };

  const hasDraftChanges = (() => {
    const originalPrimary = selectedUserRoles[0] ?? "";
    if (selectedUserRoles.length > 1) return true;
    return originalPrimary !== draftRole;
  })();

  const saveManageRoles = async () => {
    if (!selectedUser) return;
    if (!isAdmin || isModeratorOnly) return;
    const originalPrimary = selectedUserRoles[0] ?? "";
    const toRemove = selectedUserRoles.filter((role) => role !== draftRole);
    const toAdd =
      draftRole && draftRole !== originalPrimary ? [draftRole] : [];

    if (toAdd.length === 0 && toRemove.length === 0 && selectedUserRoles.length <= 1) {
      toast({
        title: "No changes",
        description: "No role updates to save.",
        status: "info",
        duration: 2500,
        isClosable: true,
      });
      closeManageRoles();
      return;
    }

    setIsSavingRoles(true);
    const failedOps: string[] = [];
    try {
      for (const roleName of toRemove) {
        try {
          await roleService.removeRole(selectedUser.id, roleName);
        } catch {
          failedOps.push(`remove:${roleName}`);
        }
      }
      for (const roleName of toAdd) {
        try {
          await roleService.assignRole(selectedUser.id, roleName);
        } catch {
          failedOps.push(`assign:${roleName}`);
        }
      }

      const refreshed = await roleService.getUserRoles(selectedUser.id);
      setSelectedUserRoles(refreshed.roles);

      if (failedOps.length === 0) {
        toast({
          title: "Roles updated",
          description: `Updated roles for ${selectedUser.username}.`,
          status: "success",
          duration: 3000,
          isClosable: true,
        });
      } else {
        toast({
          title: "Partially updated",
          description: `Some role changes failed (${failedOps.length}). Please retry.`,
          status: "warning",
          duration: 5000,
          isClosable: true,
        });
      }
      closeManageRoles();
    } catch (error) {
      toast({
        title: "Save failed",
        description: error instanceof Error ? error.message : "Failed to update roles",
        status: "error",
        duration: 5000,
        isClosable: true,
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
