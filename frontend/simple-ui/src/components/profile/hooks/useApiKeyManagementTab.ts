import { useState, useMemo, useCallback } from "react";
import { useToastWithDeduplication } from "../../../hooks/useToastWithDeduplication";
import authService from "../../../services/authService";
import type {
  User,
  Permission,
  AdminAPIKeyWithUserResponse,
  APIKeyUpdate,
} from "../../../types/auth";

function permissionLabel(
  raw: string | number,
  catalog: Permission[],
): string {
  if (typeof raw === "number") {
    return catalog.find((p) => p.id === raw)?.name ?? String(raw);
  }
  const s = String(raw);
  if (/^\d+$/.test(s)) {
    const id = parseInt(s, 10);
    return catalog.find((p) => p.id === id)?.name ?? s;
  }
  return s;
}

function getApiKeyHex(key: AdminAPIKeyWithUserResponse): string | null {
  const hex = key.api_key?.trim();
  return hex && hex.length === 32 ? hex : null;
}

/** Map UI selection (names and/or numeric ids) to permission IDs for the API. */
function resolvePermissionIds(
  selected: (string | number)[],
  catalog: Permission[],
): number[] {
  const ids = new Set<number>();
  for (const item of selected) {
    if (typeof item === "number" && Number.isInteger(item)) {
      ids.add(item);
      continue;
    }
    const s = String(item);
    const byName = catalog.find((p) => p.name === s)?.id;
    if (byName != null) {
      ids.add(byName);
      continue;
    }
    if (/^\d+$/.test(s)) {
      const n = parseInt(s, 10);
      if (catalog.length === 0 || catalog.some((p) => p.id === n)) {
        ids.add(n);
      }
    }
  }
  return Array.from(ids);
}

export interface UseApiKeyManagementTabOptions {
  user: User | null;
}

function mapKeysToAdminRows(
  keys: import("../../../types/auth").APIKeyResponse[],
  currentUser: User | null,
): AdminAPIKeyWithUserResponse[] {
  return keys.map((key) => ({
    ...key,
    user_id: currentUser?.user_id ?? "",
    user_email: currentUser?.email ?? "",
    username: currentUser?.username ?? "",
  }));
}

export function useApiKeyManagementTab({ user }: UseApiKeyManagementTabOptions) {
  const toast = useToastWithDeduplication();
  const [allApiKeys, setAllApiKeys] = useState<AdminAPIKeyWithUserResponse[]>([]);
  const [isLoadingAllApiKeys, setIsLoadingAllApiKeys] = useState(false);
  const [permissions, setPermissions] = useState<Permission[]>([]);
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
  });
  const [selectedKeyForView, setSelectedKeyForView] = useState<AdminAPIKeyWithUserResponse | null>(null);
  const [isViewModalOpen, setIsViewModalOpen] = useState(false);

  const handleFetchAllApiKeys = useCallback(
    async (options?: { silent?: boolean }) => {
      setIsLoadingAllApiKeys(true);
      try {
        const response = await authService.listApiKeys();
        const keys = Array.isArray(response.api_keys) ? response.api_keys : [];
        const allKeys = mapKeysToAdminRows(keys, user);
        setAllApiKeys(allKeys);
        if (permissions.length === 0) {
          try {
            const permsList = await authService.getAllPermissions();
            setPermissions(permsList);
          } catch (err) {
            console.error("Failed to fetch permissions for filter:", err);
          }
        }
        if (!options?.silent) {
          toast({
            title: "API Keys Loaded",
            description: `Loaded ${allKeys?.length} API key(s)`,
            status: "success",
            duration: 2000,
            isClosable: true,
          });
        }
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
    },
    [permissions.length, toast, user],
  );

  const handleOpenUpdateModal = async (key: AdminAPIKeyWithUserResponse) => {
    let catalog = permissions;
    if (catalog.length === 0) {
      try {
        catalog = await authService.getAllPermissions();
        setPermissions(Array.isArray(catalog) ? catalog : []);
      } catch {
        // Checkbox labels may not match until catalog loads elsewhere.
      }
    }
    setSelectedKeyForUpdate(key);
    setUpdateFormData({
      key_name: key.key_name,
      permissions: (key.permissions ?? []).map((p) => permissionLabel(p, catalog)),
    });
    setIsUpdateModalOpen(true);
  };

  const handleCloseUpdateModal = () => {
    setIsUpdateModalOpen(false);
    setSelectedKeyForUpdate(null);
    setUpdateFormData({ key_name: "", permissions: [] });
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
    const hex = getApiKeyHex(selectedKeyForUpdate);
    if (!hex) {
      toast({
        title: "Cannot update",
        description:
          "This row is missing the 32-character api_key. Refresh the list or check the auth service response.",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      return;
    }
    let catalog = permissions;
    if (catalog.length === 0) {
      try {
        catalog = await authService.getAllPermissions();
        setPermissions(Array.isArray(catalog) ? catalog : []);
      } catch {
        toast({
          title: "Error",
          description: "Could not load permissions. Try again or open the Permissions tab first.",
          status: "error",
          duration: 5000,
          isClosable: true,
        });
        return;
      }
    }
    const permissionIds = resolvePermissionIds(updateFormData.permissions ?? [], catalog);
    if (!permissionIds.length) {
      toast({
        title: "Validation Error",
        description: "Select at least one valid permission",
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    setIsUpdating(true);
    try {
      await authService.updateApiKey(hex, {
        key_name: updateFormData.key_name?.trim(),
        permissions: permissionIds,
      });
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
    setFilterPermission("all");
    setFilterActive("all");
  };

  const handleRevokeApiKey = async () => {
    if (!keyToRevoke) return;
    const hex = getApiKeyHex(keyToRevoke);
    if (!hex) {
      toast({
        title: "Cannot revoke",
        description:
          "This row is missing the 32-character api_key. Refresh the list or check the auth service response.",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
      return;
    }
    setIsRevoking(true);
    try {
      await authService.revokeApiKey(hex);
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
          if (filterPermission !== "all") {
            const has = (key.permissions ?? []).some(
              (p) => permissionLabel(p, permissions) === filterPermission,
            );
            if (!has) return false;
          }
          if (filterActive === "active" && !key.is_active) return false;
          if (filterActive === "revoked" && key.is_active) return false;
          return true;
        })
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()),
    [allApiKeys, filterPermission, filterActive, permissions],
  );

  const allUniquePermissions = useMemo(() => {
    const perms = new Set<string>();
    allApiKeys.forEach((key) =>
      (key.permissions ?? []).forEach((p) => perms.add(permissionLabel(p, permissions))),
    );
    return Array.from(perms).sort();
  }, [allApiKeys, permissions]);

  const formatPermission = (raw: string | number) => permissionLabel(raw, permissions);

  return {
    allApiKeys,
    isLoadingAllApiKeys,
    permissions,
    formatPermission,
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
