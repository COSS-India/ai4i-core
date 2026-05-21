import { useState, useMemo, useCallback } from "react";
import { useToastWithDeduplication } from "../../../hooks/useToastWithDeduplication";
import authService from "../../../services/authService";
import type {
  User,
  Permission,
  AdminAPIKeyWithUserResponse,
  APIKeyUpdate,
  APIKeyResponse,
} from "../../../types/auth";
import {
  formatApiKeyDisplayId,
  mergeApiKeyHexFromCache,
  normalizeApiKeyRecord,
  permissionLabelWithFallback,
  resolveApiKeyHex,
} from "../../../utils/apiKeyUtils";

function permissionIdFromRaw(raw: string | number): number | null {
  if (typeof raw === "number" && Number.isInteger(raw)) return raw;
  const s = String(raw);
  if (/^\d+$/.test(s)) return parseInt(s, 10);
  return null;
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

function normalizeListedKeys(keys: APIKeyResponse[]): APIKeyResponse[] {
  return mergeApiKeyHexFromCache(keys.map((key) => normalizeApiKeyRecord(key)));
}

function mapKeysToAdminRows(
  keys: APIKeyResponse[],
  currentUser: User | null,
): AdminAPIKeyWithUserResponse[] {
  return normalizeListedKeys(keys).map((key) => ({
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
  const [keyNameSearch, setKeyNameSearch] = useState("");
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

  const loadPermissionsCatalog = useCallback(async (): Promise<Permission[]> => {
    try {
      const permsList = await authService.getAllPermissions();
      const catalog = Array.isArray(permsList) ? permsList : [];
      setPermissions(catalog);
      return catalog;
    } catch (err) {
      console.error("Failed to fetch permissions for filter:", err);
      return [];
    }
  }, []);

  const handleFetchAllApiKeys = useCallback(
    async (options?: { silent?: boolean }) => {
      setIsLoadingAllApiKeys(true);
      try {
        const [response] = await Promise.all([
          authService.listApiKeys(),
          permissions.length > 0 ? Promise.resolve(permissions) : loadPermissionsCatalog(),
        ]);
        const keys = Array.isArray(response.api_keys) ? response.api_keys : [];
        setAllApiKeys(mapKeysToAdminRows(keys, user));
        if (!options?.silent) {
          toast({
            title: "API Keys Loaded",
            description: `Loaded ${keys.length} API key(s)`,
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
    [loadPermissionsCatalog, permissions, toast, user],
  );

  const handleOpenUpdateModal = async (key: AdminAPIKeyWithUserResponse) => {
    let catalog = permissions;
    if (catalog.length === 0) {
      catalog = await loadPermissionsCatalog();
    }
    setSelectedKeyForUpdate(key);
    setUpdateFormData({
      key_name: key.key_name,
      permissions: (key.permissions ?? []).map((p) => permissionLabelWithFallback(p, catalog)),
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
    const hex = resolveApiKeyHex(selectedKeyForUpdate);
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
    if (permissions.length === 0) {
      void loadPermissionsCatalog();
    }
  };

  const handleCloseViewModal = () => {
    setIsViewModalOpen(false);
    setSelectedKeyForView(null);
  };

  const handleResetFilters = () => {
    setFilterPermission("all");
    setFilterActive("all");
    setKeyNameSearch("");
  };

  const handleRevokeApiKey = async () => {
    if (!keyToRevoke) return;
    const hex = resolveApiKeyHex(keyToRevoke);
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
          const search = keyNameSearch.trim().toLowerCase();
          if (search && !(key.key_name ?? "").toLowerCase().includes(search)) {
            return false;
          }
          if (filterPermission !== "all") {
            const has = (key.permissions ?? []).some(
              (p) => permissionLabelWithFallback(p, permissions) === filterPermission,
            );
            if (!has) return false;
          }
          if (filterActive === "active" && !key.is_active) return false;
          if (filterActive === "revoked" && key.is_active) return false;
          return true;
        })
        .sort((a, b) => new Date(b.created_at ?? 0).getTime() - new Date(a.created_at ?? 0).getTime()),
    [allApiKeys, filterPermission, filterActive, keyNameSearch, permissions],
  );

  const allUniquePermissions = useMemo(() => {
    const perms = new Set<string>();
    allApiKeys.forEach((key) =>
      (key.permissions ?? []).forEach((p) =>
        perms.add(permissionLabelWithFallback(p, permissions)),
      ),
    );
    return Array.from(perms).sort((a, b) => a.localeCompare(b));
  }, [allApiKeys, permissions]);

  /** Human-readable names for the Permission filter (from catalog, not raw IDs). */
  const permissionFilterOptions = useMemo(() => {
    const idsOnKeys = new Set<number>();
    allApiKeys.forEach((key) => {
      (key.permissions ?? []).forEach((raw) => {
        const id = permissionIdFromRaw(raw);
        if (id != null) idsOnKeys.add(id);
      });
    });

    if (permissions.length > 0) {
      const fromCatalog = permissions
        .filter((p) => idsOnKeys.size === 0 || idsOnKeys.has(p.id))
        .map((p) => p.name)
        .sort((a, b) => a.localeCompare(b));
      if (fromCatalog.length > 0) return fromCatalog;
    }

    return allUniquePermissions.filter((label) => !/^\d+$/.test(label));
  }, [allApiKeys, allUniquePermissions, permissions]);

  const formatPermission = (raw: string | number) =>
    permissionLabelWithFallback(raw, permissions);

  const formatKeyId = (key: AdminAPIKeyWithUserResponse) => formatApiKeyDisplayId(key);

  return {
    allApiKeys,
    isLoadingAllApiKeys,
    permissions,
    formatPermission,
    formatKeyId,
    filterPermission,
    setFilterPermission,
    filterActive,
    setFilterActive,
    keyNameSearch,
    setKeyNameSearch,
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
    permissionFilterOptions,
    selectedKeyForView,
    isViewModalOpen,
    handleOpenViewModal,
    handleCloseViewModal,
    handleFetchAllApiKeys,
  };
}
