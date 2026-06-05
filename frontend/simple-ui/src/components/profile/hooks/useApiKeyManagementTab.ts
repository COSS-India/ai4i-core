import { useState, useMemo, useCallback } from "react";
import { useToastWithDeduplication } from "../../../hooks/useToastWithDeduplication";
import authService from "../../../services/authService";
import * as tenantService from "../../../services/tenantService";
import type {
  User,
  Permission,
  AdminAPIKeyWithUserResponse,
  APIKeyUpdate,
  APIKeyResponse,
} from "../../../types/auth";
import {
  API_KEY,
  type ApiKeyAccessContext,
  type ApiKeyDisplayStatusValue,
  getApiKeyInactiveReason,
  isApiKeyEffectivelyActive,
  isApiKeyExpired,
  resolveApiKeyDisplayStatus,
} from "../../../config/constants";
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
  const [filterActive, setFilterActive] = useState<string>(API_KEY.FILTER_STATUS.ALL);
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
  const [tenantStatus, setTenantStatus] = useState<string | null>(null);

  const apiKeyAccessContext = useMemo(
    (): ApiKeyAccessContext => ({
      userIsActive: user?.is_active,
      userTenantActive: user?.is_tenant_active,
      tenantStatus,
    }),
    [user?.is_active, user?.is_tenant_active, tenantStatus]
  );

  const resolveKeyDisplayStatus = useCallback(
    (key: APIKeyResponse): ApiKeyDisplayStatusValue =>
      resolveApiKeyDisplayStatus(key, apiKeyAccessContext),
    [apiKeyAccessContext]
  );

  const getKeyInactiveReason = useCallback(
    (key: APIKeyResponse): string | null => {
      const status = resolveKeyDisplayStatus(key);
      if (status !== API_KEY.DISPLAY_STATUS.INACTIVE) return null;
      if (isApiKeyExpired(key.expires_at)) {
        return "This API key has expired.";
      }
      return getApiKeyInactiveReason(apiKeyAccessContext);
    },
    [apiKeyAccessContext, resolveKeyDisplayStatus]
  );

  const loadTenantContext = useCallback(async () => {
    const tenantId = user?.tenant_id?.trim();
    if (!tenantId) {
      setTenantStatus(null);
      return;
    }
    try {
      const tenant = await tenantService.getViewTenant(tenantId);
      setTenantStatus(tenant?.status ?? null);
    } catch (err) {
      console.error("Failed to load tenant context for API keys:", err);
      setTenantStatus(null);
    }
  }, [user?.tenant_id]);

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
          loadTenantContext(),
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
    [loadPermissionsCatalog, loadTenantContext, permissions, toast, user],
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
    if (permissions.length === 0) {
      void loadPermissionsCatalog();
    }
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
          if (filterActive !== API_KEY.FILTER_STATUS.ALL) {
            const displayStatus = resolveApiKeyDisplayStatus(key, apiKeyAccessContext);
            if (displayStatus !== filterActive) return false;
          }
          return true;
        })
        .sort((a, b) => new Date(b.created_at ?? 0).getTime() - new Date(a.created_at ?? 0).getTime()),
    [allApiKeys, apiKeyAccessContext, filterPermission, filterActive, keyNameSearch, permissions],
  );

  /** Static permission names for the filter dropdown (full catalog, not keyed to loaded keys). */
  const permissionFilterOptions = useMemo(
    () =>
      permissions
        .map((p) => p.name)
        .filter(Boolean)
        .sort((a, b) => a.localeCompare(b)),
    [permissions],
  );

  const formatPermission = (permissionId: number | string) =>
    permissionLabelWithFallback(permissionId, permissions);

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
    permissionFilterOptions,
    selectedKeyForView,
    isViewModalOpen,
    handleOpenViewModal,
    handleCloseViewModal,
    handleFetchAllApiKeys,
    apiKeyAccessContext,
    resolveKeyDisplayStatus,
    getKeyInactiveReason,
    isKeyEffectivelyActive: (key: APIKeyResponse) =>
      isApiKeyEffectivelyActive(key, apiKeyAccessContext),
    isKeyRevocable: (key: APIKeyResponse) => key.is_active !== false && key.is_revoked !== true,
  };
}
