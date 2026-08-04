import { useState, useMemo, useCallback } from "react";
import { showToast } from "../../../utils/toast";
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
  getApiKeyRevokedReason,
  isApiKeyEffectivelyActive,
  isApiKeyExpired,
  resolveApiKeyDisplayStatus,
} from "../../../config/constants";
import { normalizeApiKeyRecord } from "../../../utils/apiKeyUtils";
import { useInferenceTypes } from "../../../hooks/useInferenceTypes";
import type { InferenceTypeItem } from "../../../services/inferenceTypesService";

export interface UseApiKeyManagementTabOptions {
  user: User | null;
}

/** Gate permission catalog by ENABLED_TASK_TYPES (same rules as create API key). */
function filterPermissionsByEnabledTaskTypes(
  permissions: Permission[],
  taskTypeNames: string[],
  inferenceTypes: InferenceTypeItem[],
): Permission[] {
  const named = [...permissions].filter((p) => p.name);
  if (taskTypeNames.length === 0) {
    return named.sort((a, b) => a.label.localeCompare(b.label));
  }
  const enabled = new Set(taskTypeNames.map((t) => t.trim().toLowerCase()));
  const knownTaskTypes = new Set(
    inferenceTypes.map((t) => t.name.trim().toLowerCase()),
  );
  return named
    .filter((p) => {
      const prefix = p.name.split(".")[0]?.toLowerCase() ?? "";
      return knownTaskTypes.has(prefix) ? enabled.has(prefix) : true;
    })
    .sort((a, b) => a.label.localeCompare(b.label));
}

function mapKeysToAdminRows(
  keys: APIKeyResponse[],
  currentUser: User | null,
): AdminAPIKeyWithUserResponse[] {
  return keys.map(normalizeApiKeyRecord).map((key) => ({
    ...key,
    user_id: currentUser?.user_id ?? "",
    user_email: currentUser?.email ?? "",
    username: currentUser?.username ?? "",
  }));
}

export function useApiKeyManagementTab({ user }: UseApiKeyManagementTabOptions) {
  const { taskTypeNames, inferenceTypes } = useInferenceTypes();
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

  const getKeyRevokedReason = useCallback(
    (key: APIKeyResponse): string | null => {
      const status = resolveKeyDisplayStatus(key);
      if (status !== API_KEY.DISPLAY_STATUS.REVOKED) return null;
      return getApiKeyRevokedReason(apiKeyAccessContext);
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
          showToast({
            type: "success",
            message: `Loaded ${keys.length} API key(s)`,
          });
        }
      } catch (error) {
        showToast({
          type: "error",
          message: error instanceof Error ? error.message : "Failed to load API keys",
        });
      } finally {
        setIsLoadingAllApiKeys(false);
      }
    },
    [loadPermissionsCatalog, loadTenantContext, permissions, user],
  );

  const handleOpenUpdateModal = async (key: AdminAPIKeyWithUserResponse) => {
    const catalog =
      permissions.length === 0 ? await loadPermissionsCatalog() : permissions;
    // Same ENABLED_TASK_TYPES gate as create / filter dropdown — only show
    // assignable permissions (e.g. llm-only when ENABLED_TASK_TYPES=llm).
    const allowedNames = new Set(
      filterPermissionsByEnabledTaskTypes(catalog, taskTypeNames, inferenceTypes).map(
        (p) => p.name,
      ),
    );
    setSelectedKeyForUpdate(key);
    setUpdateFormData({
      key_name: key.key_name,
      permissions: (key.permissions ?? []).filter((name) => allowedNames.has(name)),
    });
    setIsUpdateModalOpen(true);
  };

  const permissionFilterOptions = useMemo(
    () => filterPermissionsByEnabledTaskTypes(permissions, taskTypeNames, inferenceTypes),
    [permissions, taskTypeNames, inferenceTypes],
  );

  const handleCloseUpdateModal = () => {
    setIsUpdateModalOpen(false);
    setSelectedKeyForUpdate(null);
    setUpdateFormData({ key_name: "", permissions: [] });
  };

  const handleUpdateApiKey = async () => {
    if (!selectedKeyForUpdate) return;
    if (!updateFormData.key_name?.trim()) {
      showToast({ type: "error", message: "Please enter a key name" });
      return;
    }
    const allowedNames = new Set(permissionFilterOptions.map((p) => p.name));
    const nextPermissions = (updateFormData.permissions ?? []).filter((name) =>
      allowedNames.has(name),
    );
    if (!nextPermissions.length) {
      showToast({ type: "error", message: "Please select at least one permission" });
      return;
    }
    setIsUpdating(true);
    try {
      await authService.updateApiKey(selectedKeyForUpdate.id, {
        key_name: updateFormData.key_name?.trim(),
        permissions: nextPermissions,
      });
      showToast({ type: "success", message: "API key has been updated successfully" });
      handleCloseUpdateModal();
      await handleFetchAllApiKeys();
    } catch (error) {
      showToast({
        type: "error",
        message: error instanceof Error ? error.message : "Failed to update API key",
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
    setIsRevoking(true);
    try {
      await authService.revokeApiKey(keyToRevoke.id);
      showToast({ type: "success", message: "API key has been revoked successfully" });
      handleCloseRevokeModal();
      await handleFetchAllApiKeys();
    } catch (error) {
      showToast({
        type: "error",
        message: error instanceof Error ? error.message : "Failed to revoke API key",
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
            if (!(key.permissions ?? []).includes(filterPermission)) return false;
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

  const formatPermission = (permissionName: string) =>
    permissions.find((p) => p.name === permissionName)?.label ?? permissionName;

  const formatKeyId = (key: AdminAPIKeyWithUserResponse) => key.api_key ?? "—";

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
    getKeyRevokedReason,
    isKeyEffectivelyActive: (key: APIKeyResponse) =>
      isApiKeyEffectivelyActive(key, apiKeyAccessContext),
    isKeyRevocable: (key: APIKeyResponse) => key.is_active !== false && key.is_revoked !== true,
  };
}
