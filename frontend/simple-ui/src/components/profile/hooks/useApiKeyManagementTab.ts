import { useState, useMemo } from "react";
import { useToast } from "@chakra-ui/react";
import authService from "../../../services/authService";
import type { User } from "../../../types/auth";
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
  const toast = useToast();
  const [allApiKeys, setAllApiKeys] = useState<AdminAPIKeyWithUserResponse[]>([]);
  const [isLoadingAllApiKeys, setIsLoadingAllApiKeys] = useState(false);
  const [permissions, setPermissions] = useState<string[]>([]);
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
      const allKeys = await authService.listAllApiKeys();
      setAllApiKeys(allKeys);
      if (permissions.length === 0) {
        try {
          const permsList = await authService.getAllPermissions();
          setPermissions(permsList);
        } catch (err) {
          console.error("Failed to fetch permissions for filter:", err);
        }
      }
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

  const handleOpenUpdateModal = (key: AdminAPIKeyWithUserResponse) => {
    setSelectedKeyForUpdate(key);
    setUpdateFormData({
      key_name: key.key_name,
      permissions: [...key.permissions],
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
    setIsUpdating(true);
    try {
      await authService.updateApiKey(selectedKeyForUpdate.id, updateFormData);
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
      await authService.revokeApiKey(keyToRevoke.id);
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
          if (filterPermission !== "all" && !key.permissions.includes(filterPermission)) return false;
          if (filterActive === "active" && !key.is_active) return false;
          if (filterActive === "inactive" && key.is_active) return false;
          return true;
        })
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    [allApiKeys, filterUser, filterPermission, filterActive]
  );

  const allUniquePermissions = useMemo(() => {
    const perms = new Set<string>();
    allApiKeys.forEach((key) => key.permissions.forEach((p) => perms.add(p)));
    return Array.from(perms).sort();
  }, [allApiKeys]);

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
    selectedKeyForView,
    isViewModalOpen,
    handleOpenViewModal,
    handleCloseViewModal,
    handleFetchAllApiKeys,
  };
}
