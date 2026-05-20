import { useState, useMemo } from "react";
import { useToastWithDeduplication } from "../../../hooks/useToastWithDeduplication";
import authService from "../../../services/authService";
import type { User, Permission } from "../../../types/auth";
import type { AdminAPIKeyWithUserResponse, APIKeyUpdate } from "../../../types/auth";

export interface UseApiKeyManagementTabOptions {
  user: User | null;
  users: User[];
  isLoadingUsers: boolean;
}

export function useApiKeyManagementTab({
  user,
  users,
}: UseApiKeyManagementTabOptions) {
  const toast = useToastWithDeduplication();
  const [allApiKeys, setAllApiKeys] = useState<AdminAPIKeyWithUserResponse[]>([]);
  const [isLoadingAllApiKeys, setIsLoadingAllApiKeys] = useState(false);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [filterUser, setFilterUser] = useState("all");
  const [filterPermission, setFilterPermission] = useState("all");
  const [filterActive, setFilterActive] = useState("all");
  const [selectedKeyForUpdate, setSelectedKeyForUpdate] = useState<AdminAPIKeyWithUserResponse | null>(null);
  const [isUpdateModalOpen, setIsUpdateModalOpen] = useState(false);
  const [isRevokeModalOpen, setIsRevokeModalOpen] = useState(false);
  const [keyToRevoke, setKeyToRevoke] = useState<AdminAPIKeyWithUserResponse | null>(null);
  const [isRevoking, setIsRevoking] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateFormData, setUpdateFormData] = useState<APIKeyUpdate>({
    key_name: "",
    permissions: [],
    is_active: true,
  });
  const [selectedKeyForView, setSelectedKeyForView] = useState<AdminAPIKeyWithUserResponse | null>(null);
  const [isViewModalOpen, setIsViewModalOpen] = useState(false);

  const handleFetchAllApiKeys = async () => {
    setIsLoadingAllApiKeys(true);
    try {
      // Load permissions first (if not already loaded)
      if (permissions.length === 0) {
        try {
          const permsList = await authService.getAllPermissions();
          setPermissions(permsList);
        } catch (err) {
          console.error("Failed to fetch permissions for filter:", err);
        }
      }

      // Then load API keys
      const allKeys = await authService.listAllApiKeys();
      setAllApiKeys(allKeys);

      toast({
        title: "API Keys Loaded",
        description: `Loaded ${allKeys?.length} API key(s)`,
        status: "success",
        duration: 2000,
        isClosable: true,
      });
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to load API keys",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsLoadingAllApiKeys(false);
    }
  };

  const handleOpenUpdateModal = async (key: AdminAPIKeyWithUserResponse) => {
    // Ensure permissions are loaded before opening modal
    if (permissions.length === 0) {
      try {
        const permsList = await authService.getAllPermissions();
        setPermissions(permsList);
      } catch (err) {
        console.error("Failed to load permissions:", err);
      }
    }

    setSelectedKeyForUpdate(key);
    setUpdateFormData({
      key_name: key.key_name,
      permissions: key.permissions ? key.permissions.map(p => (typeof p === 'string' ? parseInt(p, 10) : p)) : [],
      is_active: key.is_active,
    });
    setIsUpdateModalOpen(true);
  };

  const handleCloseUpdateModal = () => {
    setIsUpdateModalOpen(false);
    setSelectedKeyForUpdate(null);
    setUpdateFormData({ key_name: "", permissions: [], is_active: true });
  };

  const handleUpdateApiKey = async () => {
    if (!selectedKeyForUpdate) return;
    if (!updateFormData.key_name?.trim()) {
      toast({
        title: "Validation Error",
        description: "Please enter a key name",
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    if (!updateFormData.permissions?.length) {
      toast({
        title: "Validation Error",
        description: "Please select at least one permission",
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    setIsUpdating(true);
    try {
      await authService.updateApiKey(selectedKeyForUpdate.api_key || selectedKeyForUpdate.id.toString(), updateFormData);
      toast({
        title: "API Key Updated",
        description: "API key has been updated successfully",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      handleCloseUpdateModal();
      await handleFetchAllApiKeys();
    } catch (error) {
      toast({
        title: "Update Failed",
        description: error instanceof Error ? error.message : "Failed to update API key",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsUpdating(false);
    }
  };

  const handleOpenRevokeModal = (key: AdminAPIKeyWithUserResponse) => {
    setKeyToRevoke(key);
    setIsRevokeModalOpen(true);
  };

  const handleCloseRevokeModal = () => {
    setIsRevokeModalOpen(false);
    setKeyToRevoke(null);
  };

  const handleOpenViewModal = (key: AdminAPIKeyWithUserResponse) => {
    setSelectedKeyForView(key);
    setIsViewModalOpen(true);
  };

  const handleCloseViewModal = () => {
    setIsViewModalOpen(false);
    setSelectedKeyForView(null);
  };

  const handleResetFilters = () => {
    setFilterUser("all");
    setFilterPermission("all");
    setFilterActive("all");
  };

  const handleRevokeApiKey = async () => {
    if (!keyToRevoke) return;
    setIsRevoking(true);
    try {
      await authService.revokeApiKey(keyToRevoke.api_key || keyToRevoke.id.toString());
      toast({
        title: "API Key Revoked",
        description: "API key has been revoked successfully",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
      handleCloseRevokeModal();
      await handleFetchAllApiKeys();
    } catch (error) {
      toast({
        title: "Revoke Failed",
        description: error instanceof Error ? error.message : "Failed to revoke API key",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsRevoking(false);
    }
  };

  const filteredApiKeys = useMemo(
    () =>
      [...allApiKeys]
        .filter((key) => {
          if (filterUser !== "all" && key.user_id.toString() !== filterUser) return false;
          if (filterPermission !== "all") {
            // Handle both numeric IDs and string names
            const permissionMatch = key.permissions.some((perm) => {
              if (typeof perm === 'number') {
                // If perm is a number, find its name and compare
                const permName = permissions.find(p => p.id === perm)?.name;
                return permName === filterPermission || perm === parseInt(filterPermission, 10);
              }
              return perm === filterPermission;
            });
            if (!permissionMatch) return false;
          }
          if (filterActive === "active" && !key.is_active) return false;
          if (filterActive === "inactive" && key.is_active) return false;
          return true;
        })
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    [allApiKeys, filterUser, filterPermission, filterActive, permissions]
  );

  const allUniquePermissions = useMemo(() => {
    const perms = new Set<string>();
    allApiKeys.forEach((key) => key.permissions.forEach((p) => perms.add(String(p))));
    return Array.from(perms).sort();
  }, [allApiKeys]);

  const permissionOptionsForFilter = useMemo(() => {
    if (allUniquePermissions.length > 0) {
      return allUniquePermissions.map((perm) => {
        // Handle both numeric IDs and string names
        if (!isNaN(Number(perm))) {
          const permId = parseInt(perm, 10);
          // Try to find permission name, fallback to showing the ID
          return permissions.find(p => p.id === permId)?.name || String(permId);
        }
        return perm;
      });
    }
    // If no unique permissions from keys, show loaded permissions
    if (permissions.length > 0) {
      return permissions.map((p) => p.name);
    }
    // If no permissions loaded, return empty array (dropdown will show "All Permissions" only)
    return [];
  }, [allUniquePermissions, permissions]);

  return {
    allApiKeys,
    isLoadingAllApiKeys,
    permissions,
    users,
    filterUser,
    setFilterUser,
    filterPermission,
    setFilterPermission,
    filterActive,
    setFilterActive,
    selectedKeyForUpdate,
    updateFormData,
    setUpdateFormData,
    isUpdateModalOpen,
    handleOpenUpdateModal,
    handleCloseUpdateModal,
    handleUpdateApiKey,
    isRevokeModalOpen,
    keyToRevoke,
    handleOpenRevokeModal,
    handleCloseRevokeModal,
    handleRevokeApiKey,
    isRevoking,
    isUpdating,
    handleResetFilters,
    filteredApiKeys,
    allUniquePermissions,
    permissionOptionsForFilter,
    selectedKeyForView,
    isViewModalOpen,
    handleOpenViewModal,
    handleCloseViewModal,
    handleFetchAllApiKeys,
  };
}
