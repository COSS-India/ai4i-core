import { useState } from "react";
import { useToastWithDeduplication } from "../../../hooks/useToastWithDeduplication";
import roleService, { Role } from "../../../services/roleService";
import type { User } from "../../../types/auth";

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
  const [selectedRole, setSelectedRole] = useState("");
  const [isLoadingRoles, setIsLoadingRoles] = useState(false);
  const [isLoadingUserRoles, setIsLoadingUserRoles] = useState(false);
  const [isAssigningRole, setIsAssigningRole] = useState(false);

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

  const handleUserSelect = async (userId: number) => {
    const u = users.find((x) => x.id === userId);
    if (u) {
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
    } else {
      setSelectedUser(null);
      setSelectedUserRoles([]);
    }
  };

  const handleAssignRole = async () => {
    if (!selectedUser || !selectedRole) {
      toast({
        title: "Validation Error",
        description: "Please select a role",
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    setIsAssigningRole(true);
    try {
      await roleService.assignRole(selectedUser.id, selectedRole);
      toast({
        title: "Success",
        description: `Role ${selectedRole} assigned to user ${selectedUser.username}`,
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      const userRolesData = await roleService.getUserRoles(selectedUser.id);
      setSelectedUserRoles(userRolesData.roles);
      setSelectedRole("");
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to assign role",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsAssigningRole(false);
    }
  };

  return {
    roles,
    selectedUser,
    selectedUserRoles,
    selectedRole,
    setSelectedRole,
    isLoadingRoles,
    isLoadingUserRoles,
    isAssigningRole,
    isAdmin,
    isModeratorOnly,
    handleLoadRoles,
    handleUserSelect,
    handleAssignRole,
  };
}
