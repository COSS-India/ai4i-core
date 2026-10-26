import { useState, useMemo, useCallback, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { showToast } from "../../../utils/toast";
import authService from "../../../services/authService";
import * as tenantService from "../../../services/tenantService";
import {
  flattenApiKeyGroups,
  listGroupedApiKeys,
  toLegacyApiKeyResponse,
} from "../../../services/apiKeyService";
import { fetchApplicationUsageDetail } from "../../../services/applicationUsageService";
import type {
  User,
  Permission,
  APIKeyUpdate,
  APIKeyResponse,
  RotateAPIKeyResponse,
} from "../../../types/auth";
import type { Application } from "../../../types/application";
import {
  API_KEY,
  type ApiKeyAccessContext,
  type ApiKeyDisplayStatusValue,
  getApiKeyInactiveReason,
  getApiKeyRevokedReason,
  isApiKeyEffectivelyActive,
  isApiKeyExpired,
  isApiKeyWithoutLiveValue,
  resolveApiKeyDisplayStatus,
} from "../../../config/constants";
import {
  formatPermissionLabel,
  DEFAULT_GRACE_EXTENSION,
  type GraceExtensionOption,
  graceExtensionEnd,
  graceExtensionError,
  isRotationInProgress,
  normalizeApiKeyRecord,
} from "../../../utils/apiKeyUtils";
import { getDefaultRotationGraceDays } from "../../../config/runtimeConfig";
import { useInferenceTypes } from "../../../hooks/useInferenceTypes";
import {
  API_KEY_CATALOG_STALE_MS,
  API_KEY_PERMISSIONS_QUERY_KEY,
  fetchPermissionCatalog,
  fetchTenantApplications,
  tenantApplicationsQueryKey,
} from "./apiKeyCatalogQueries";
import type { InferenceTypeItem } from "../../../services/inferenceTypesService";

export interface ApiKeyTableRow extends APIKeyResponse {
  application_name?: string;
  /** Set on the Current/Previous key sub-rows the table shows under a rotating key. */
  subRow?: "current" | "previous";
}

/** Null until revoke opens. Error must not be rendered as ₹0. */
export type RevokeBudgetSummary =
  | { status: "loading" }
  | { status: "error" }
  | {
      status: "ready";
      allocated: number;
      consumed: number;
      unused: number;
      applicationName: string;
    };

export interface UseApiKeyManagementTabOptions {
  user: User | null;
}

function isPermissionEnabledForTaskTypes(
  permissionName: string,
  taskTypeNames: string[],
  inferenceTypes: InferenceTypeItem[],
): boolean {
  if (taskTypeNames.length === 0) return true;
  const prefix = permissionName.split(".")[0]?.toLowerCase() ?? "";
  const enabled = new Set(taskTypeNames.map((t) => t.trim().toLowerCase()));
  const knownTaskTypes = new Set(
    inferenceTypes.map((t) => t.name.trim().toLowerCase()),
  );
  return knownTaskTypes.has(prefix) ? enabled.has(prefix) : true;
}

function filterPermissionsByEnabledTaskTypes(
  permissions: Permission[],
  taskTypeNames: string[],
  inferenceTypes: InferenceTypeItem[],
): Permission[] {
  return [...permissions]
    .filter((p) => p.name)
    .filter((p) =>
      isPermissionEnabledForTaskTypes(p.name, taskTypeNames, inferenceTypes),
    )
    .sort((a, b) => a.label.localeCompare(b.label));
}

function mapKeysToRows(
  keys: APIKeyResponse[],
  applications: Application[],
): ApiKeyTableRow[] {
  const appNameById = new Map(
    applications.map((a) => [a.application_id, a.name]),
  );
  return keys.map(normalizeApiKeyRecord).map((key) => ({
    ...key,
    application_name:
      key.application_name ||
      (key.application_id
        ? appNameById.get(key.application_id) ?? key.application_id
        : undefined),
  }));
}

export function useApiKeyManagementTab({ user }: UseApiKeyManagementTabOptions) {
  const queryClient = useQueryClient();
  const { taskTypeNames, inferenceTypes } = useInferenceTypes();
  const [allApiKeys, setAllApiKeys] = useState<ApiKeyTableRow[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [isLoadingAllApiKeys, setIsLoadingAllApiKeys] = useState(false);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [filterApplication, setFilterApplication] = useState("all");
  const [filterPermission, setFilterPermission] = useState("all");
  const [filterActive, setFilterActive] = useState<string>(API_KEY.FILTER_STATUS.ALL);
  const [keyNameSearch, setKeyNameSearch] = useState("");
  const [selectedKeyForUpdate, setSelectedKeyForUpdate] = useState<ApiKeyTableRow | null>(null);
  const [isUpdateModalOpen, setIsUpdateModalOpen] = useState(false);
  const [isRevokeModalOpen, setIsRevokeModalOpen] = useState(false);
  const [keyToRevoke, setKeyToRevoke] = useState<ApiKeyTableRow | null>(null);
  const [revokeBudget, setRevokeBudget] = useState<RevokeBudgetSummary | null>(null);
  const revokeLoadRef = useRef(0);
  const [isRevoking, setIsRevoking] = useState(false);
  const [keyToRotate, setKeyToRotate] = useState<ApiKeyTableRow | null>(null);
  const [isRotating, setIsRotating] = useState(false);
  /** Key whose previous (pre-rotation) value the admin is about to stop early. */
  const [keyToStopPrevious, setKeyToStopPrevious] = useState<ApiKeyTableRow | null>(null);
  const [isStoppingPrevious, setIsStoppingPrevious] = useState(false);
  /** Grace days in the rotate dialog, prefilled with the default; required to rotate. */
  const [rotateGraceDays, setRotateGraceDays] = useState("");
  /** Prefilled grace period (ROTATED_API_KEY_DEFAULT_GRACE_DAYS); null when not configured. */
  const defaultGraceDays = getDefaultRotationGraceDays();
  /** Key whose previous value's window the admin is about to extend. */
  const [keyToExtend, setKeyToExtend] = useState<ApiKeyTableRow | null>(null);
  /** Preset added to the current grace end, or "custom" for extendCustomUntil. */
  const [extendOption, setExtendOption] = useState<GraceExtensionOption>(DEFAULT_GRACE_EXTENSION);
  /** Custom new grace end as a datetime-local input value. */
  const [extendCustomUntil, setExtendCustomUntil] = useState("");
  const [isExtending, setIsExtending] = useState(false);
  /** Key whose current value the admin is about to revoke on its own. */
  const [keyToRevokeCurrent, setKeyToRevokeCurrent] = useState<ApiKeyTableRow | null>(null);
  const [isRevokingCurrent, setIsRevokingCurrent] = useState(false);
  /** The new raw key, held only until the admin closes the result dialog. */
  const [rotatedKey, setRotatedKey] = useState<RotateAPIKeyResponse | null>(null);
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateFormData, setUpdateFormData] = useState<APIKeyUpdate>({
    key_name: "",
    permissions: [],
  });
  const [selectedKeyForView, setSelectedKeyForView] = useState<ApiKeyTableRow | null>(null);
  const [isViewModalOpen, setIsViewModalOpen] = useState(false);
  const [tenantStatus, setTenantStatus] = useState<string | null>(null);
  const applicationsRef = useRef(applications);
  const permissionsRef = useRef(permissions);
  applicationsRef.current = applications;
  permissionsRef.current = permissions;

  const apiKeyAccessContext = useMemo(
    (): ApiKeyAccessContext => ({
      userIsActive: user?.is_active,
      userTenantActive: user?.is_tenant_active,
      tenantStatus,
    }),
    [user?.is_active, user?.is_tenant_active, tenantStatus],
  );

  const resolveKeyDisplayStatus = useCallback(
    (key: APIKeyResponse): ApiKeyDisplayStatusValue =>
      resolveApiKeyDisplayStatus(key, apiKeyAccessContext),
    [apiKeyAccessContext],
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
    [apiKeyAccessContext, resolveKeyDisplayStatus],
  );

  const getKeyRevokedReason = useCallback(
    (key: APIKeyResponse): string | null => {
      const status = resolveKeyDisplayStatus(key);
      if (status !== API_KEY.DISPLAY_STATUS.REVOKED) return null;
      if (key.is_active !== false && isApiKeyWithoutLiveValue(key)) {
        return "The current key was revoked during a rotation and the previous key's grace period has ended.";
      }
      return getApiKeyRevokedReason(apiKeyAccessContext);
    },
    [apiKeyAccessContext, resolveKeyDisplayStatus],
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

  const loadApplications = useCallback(async (): Promise<Application[]> => {
    const tenantId = user?.tenant_id?.trim();
    if (!tenantId) {
      setApplications([]);
      return [];
    }
    try {
      const apps = await queryClient.fetchQuery({
        queryKey: tenantApplicationsQueryKey(tenantId),
        queryFn: () => fetchTenantApplications(tenantId),
        staleTime: API_KEY_CATALOG_STALE_MS,
      });
      setApplications(apps);
      return apps;
    } catch (err) {
      console.error("Failed to load applications for API keys:", err);
      setApplications([]);
      return [];
    }
  }, [queryClient, user?.tenant_id]);

  const loadPermissionsCatalog = useCallback(async (): Promise<Permission[]> => {
    try {
      const catalog = await queryClient.fetchQuery({
        queryKey: API_KEY_PERMISSIONS_QUERY_KEY,
        queryFn: fetchPermissionCatalog,
        staleTime: API_KEY_CATALOG_STALE_MS,
      });
      setPermissions(catalog);
      return catalog;
    } catch (err) {
      console.error("Failed to fetch permissions for filter:", err);
      return [];
    }
  }, [queryClient]);

  const handleFetchAllApiKeys = useCallback(
    async (options?: { silent?: boolean }) => {
      const tenantId = user?.tenant_id?.trim();
      if (!tenantId) {
        setAllApiKeys([]);
        return;
      }

      setIsLoadingAllApiKeys(true);
      try {
        const cachedApps = applicationsRef.current;
        const cachedPerms = permissionsRef.current;
        const [grouped, apps] = await Promise.all([
          listGroupedApiKeys(tenantId),
          cachedApps.length > 0 ? Promise.resolve(cachedApps) : loadApplications(),
        ]);
        await Promise.all([
          cachedPerms.length > 0 ? Promise.resolve(cachedPerms) : loadPermissionsCatalog(),
          loadTenantContext(),
        ]);
        const flat = flattenApiKeyGroups(grouped.groups).map((k) =>
          toLegacyApiKeyResponse(k),
        );
        setAllApiKeys(mapKeysToRows(flat, apps));
        if (!options?.silent) {
          showToast({
            type: "success",
            message: `Loaded ${flat.length} API key(s)`,
          });
        }
      } catch {
        showToast({
          type: "error",
          message: "Unable to load API keys. Please try again.",
        });
      } finally {
        setIsLoadingAllApiKeys(false);
      }
    },
    [loadApplications, loadPermissionsCatalog, loadTenantContext, user?.tenant_id],
  );

  const handleOpenUpdateModal = async (key: ApiKeyTableRow) => {
    const catalog =
      permissions.length === 0 ? await loadPermissionsCatalog() : permissions;
    const allowedNames = new Set(
      filterPermissionsByEnabledTaskTypes(catalog, taskTypeNames, inferenceTypes).map(
        (p) => p.name,
      ),
    );
    const existing = key.permissions ?? [];
    const assignable = existing.filter((name) => allowedNames.has(name));
    const droppedCount = existing.length - assignable.length;
    setSelectedKeyForUpdate(key);
    setUpdateFormData({
      key_name: key.key_name,
      permissions: assignable,
    });
    setIsUpdateModalOpen(true);
    if (droppedCount > 0) {
      showToast({
        type: "warning",
        message:
          droppedCount === 1
            ? "1 permission no longer available was removed from the selection"
            : `${droppedCount} permissions no longer available were removed from the selection`,
      });
    }
  };

  const permissionFilterOptions = useMemo(
    () => filterPermissionsByEnabledTaskTypes(permissions, taskTypeNames, inferenceTypes),
    [permissions, taskTypeNames, inferenceTypes],
  );

  const applicationFilterOptions = useMemo(
    () =>
      [...applications]
        .filter((a) => a.status === "ACTIVE")
        .sort((a, b) => a.name.localeCompare(b.name)),
    [applications],
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
    const originalPermissions = selectedKeyForUpdate.permissions ?? [];
    const droppedCount = originalPermissions.filter((name) => !allowedNames.has(name)).length;
    setIsUpdating(true);
    try {
      await authService.updateApiKey(selectedKeyForUpdate.id, {
        key_name: updateFormData.key_name?.trim(),
        permissions: nextPermissions,
      });
      let message = "API key has been updated successfully";
      if (droppedCount > 0) {
        message =
          droppedCount === 1
            ? "API key updated; 1 permission no longer available was removed"
            : `API key updated; ${droppedCount} permissions no longer available were removed`;
      }
      showToast({ type: "success", message });
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

  const handleOpenRevokeModal = (key: ApiKeyTableRow) => {
    setKeyToRevoke(key);
    setIsRevokeModalOpen(true);
    if (permissions.length === 0) {
      void loadPermissionsCatalog();
    }
    const loadId = ++revokeLoadRef.current;
    setRevokeBudget({ status: "loading" });
    const tenantId = user?.tenant_id?.trim();
    const applicationId = Number(key.application_id);
    if (!tenantId || !Number.isFinite(applicationId) || applicationId <= 0) {
      setRevokeBudget({ status: "error" });
      return;
    }
    void fetchApplicationUsageDetail(tenantId, applicationId)
      .then((detail) => {
        if (revokeLoadRef.current !== loadId) return;
        const match = detail.apiKeys.find((item) => item.keyId === key.id);
        const allocated = match?.allocatedBudget.amount;
        const consumed = match?.spendBudget.amount;
        if (
          !match ||
          allocated == null ||
          consumed == null ||
          !Number.isFinite(allocated) ||
          !Number.isFinite(consumed)
        ) {
          setRevokeBudget({ status: "error" });
          return;
        }
        const applicationName =
          detail.applicationName?.trim() ||
          key.application_name?.trim() ||
          "the parent Application";
        setRevokeBudget({
          status: "ready",
          allocated,
          consumed,
          unused: Math.round((allocated - consumed) * 100) / 100,
          applicationName,
        });
      })
      .catch(() => {
        if (revokeLoadRef.current !== loadId) return;
        setRevokeBudget({ status: "error" });
      });
  };

  const handleCloseRevokeModal = () => {
    revokeLoadRef.current += 1;
    setIsRevokeModalOpen(false);
    setKeyToRevoke(null);
    setRevokeBudget(null);
  };

  const handleOpenViewModal = (key: ApiKeyTableRow) => {
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
    setFilterApplication("all");
    setFilterPermission("all");
    setFilterActive(API_KEY.FILTER_STATUS.ALL);
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

  const handleOpenRotateModal = (key: ApiKeyTableRow) => {
    setRotateGraceDays(defaultGraceDays == null ? "" : String(defaultGraceDays));
    setKeyToRotate(key);
  };

  /** Whole days ≥ 0; null when blank or invalid (rotate requires a value). */
  const rotateGraceDaysValue = ((): number | null => {
    const raw = rotateGraceDays.trim();
    if (!/^\d+$/.test(raw)) return null;
    return Number(raw);
  })();

  const handleCloseRotateModal = () => {
    if (!isRotating) setKeyToRotate(null);
  };

  const handleRotateApiKey = async () => {
    if (!keyToRotate) return;
    const graceDays = rotateGraceDaysValue;
    if (graceDays === null) {
      showToast({ type: "error", message: "Enter the grace period as a whole number of days (0 or more)." });
      return;
    }
    setIsRotating(true);
    try {
      const result = await authService.rotateApiKey(keyToRotate.id, graceDays);
      setKeyToRotate(null);
      setRotatedKey(result);
      await handleFetchAllApiKeys();
    } catch (error) {
      showToast({
        type: "error",
        message: error instanceof Error ? error.message : "Failed to rotate API key",
      });
      // A 409 usually means the list is stale (rotated or revoked elsewhere).
      setKeyToRotate(null);
      void handleFetchAllApiKeys();
    } finally {
      setIsRotating(false);
    }
  };

  const handleCloseRotatedKey = () => setRotatedKey(null);

  const handleOpenStopPreviousModal = (key: ApiKeyTableRow) => setKeyToStopPrevious(key);

  const handleCloseStopPreviousModal = () => {
    if (!isStoppingPrevious) setKeyToStopPrevious(null);
  };

  const handleStopPreviousKeyValue = async () => {
    if (!keyToStopPrevious) return;
    setIsStoppingPrevious(true);
    try {
      const result = await authService.revokePreviousApiKeyValue(keyToStopPrevious.id);
      showToast({ type: "success", message: result.message });
      setKeyToStopPrevious(null);
      await handleFetchAllApiKeys();
    } catch (error) {
      showToast({
        type: "error",
        message: error instanceof Error ? error.message : "Failed to revoke the previous key value",
      });
      // A 409 means the window already ended, or the key was revoked elsewhere.
      setKeyToStopPrevious(null);
      void handleFetchAllApiKeys();
    } finally {
      setIsStoppingPrevious(false);
    }
  };

  const handleOpenExtendModal = (key: ApiKeyTableRow) => {
    setExtendOption(DEFAULT_GRACE_EXTENSION);
    setExtendCustomUntil("");
    setKeyToExtend(key);
  };

  const extendNewEnd = keyToExtend
    ? graceExtensionEnd(keyToExtend.rotated_key_expires_at, extendOption, extendCustomUntil)
    : null;
  const extendError = keyToExtend
    ? graceExtensionError(extendNewEnd, keyToExtend.rotated_key_expires_at, keyToExtend.expires_at)
    : null;

  const handleCloseExtendModal = () => {
    if (!isExtending) setKeyToExtend(null);
  };

  const handleExtendPreviousKeyValue = async () => {
    if (!keyToExtend) return;
    if (extendError || !extendNewEnd) {
      showToast({ type: "error", message: extendError ?? "Choose when the previous key should stop working." });
      return;
    }
    const until = extendNewEnd;
    setIsExtending(true);
    try {
      const result = await authService.extendPreviousApiKeyValue(keyToExtend.id, until.toISOString());
      showToast({
        type: "success",
        message: `Previous key now works until ${new Date(result.rotated_key_expires_at ?? until).toLocaleString()}.`,
      });
      setKeyToExtend(null);
      await handleFetchAllApiKeys();
    } catch (error) {
      showToast({
        type: "error",
        message: error instanceof Error ? error.message : "Failed to extend the previous key",
      });
      // A 409 means the window already ended or the key changed elsewhere; a
      // 422 is a date the admin can fix, so keep the dialog open for that.
      void handleFetchAllApiKeys();
    } finally {
      setIsExtending(false);
    }
  };

  const handleOpenRevokeCurrentModal = (key: ApiKeyTableRow) => setKeyToRevokeCurrent(key);

  const handleCloseRevokeCurrentModal = () => {
    if (!isRevokingCurrent) setKeyToRevokeCurrent(null);
  };

  const handleRevokeCurrentKeyValue = async () => {
    if (!keyToRevokeCurrent) return;
    setIsRevokingCurrent(true);
    try {
      const result = await authService.revokeCurrentApiKeyValue(keyToRevokeCurrent.id);
      showToast({ type: "success", message: result.message });
      setKeyToRevokeCurrent(null);
      await handleFetchAllApiKeys();
    } catch (error) {
      showToast({
        type: "error",
        message: error instanceof Error ? error.message : "Failed to revoke the current key",
      });
      setKeyToRevokeCurrent(null);
      void handleFetchAllApiKeys();
    } finally {
      setIsRevokingCurrent(false);
    }
  };

  const visibleApiKeys = useMemo(
    () =>
      allApiKeys.filter((key) => {
        const perms = key.permissions ?? [];
        if (perms.length === 0) return true;
        return perms.some((name) =>
          isPermissionEnabledForTaskTypes(name, taskTypeNames, inferenceTypes),
        );
      }),
    [allApiKeys, taskTypeNames, inferenceTypes],
  );

  const filteredApiKeys = useMemo(
    () =>
      [...visibleApiKeys]
        .filter((key) => {
          const search = keyNameSearch.trim().toLowerCase();
          if (search && !(key.key_name ?? "").toLowerCase().includes(search)) {
            return false;
          }
          if (filterApplication !== "all") {
            if (key.application_id !== filterApplication) return false;
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
        .sort(
          (a, b) =>
            new Date(b.created_at ?? 0).getTime() - new Date(a.created_at ?? 0).getTime(),
        ),
    [
      visibleApiKeys,
      apiKeyAccessContext,
      filterApplication,
      filterPermission,
      filterActive,
      keyNameSearch,
    ],
  );

  const formatPermission = (permissionName: string) =>
    formatPermissionLabel(
      permissions.find((p) => p.name === permissionName)?.label ?? permissionName,
    );

  const visiblePermissionsForKey = useCallback(
    (key: { permissions?: string[] | null }) =>
      (key.permissions ?? []).filter((name) =>
        isPermissionEnabledForTaskTypes(name, taskTypeNames, inferenceTypes),
      ),
    [taskTypeNames, inferenceTypes],
  );

  const allocationOverview = useMemo(() => {
    const activeApps = applications.filter(
      (app) =>
        app.status === "ACTIVE" &&
        app.allocated_budget != null &&
        Number.isFinite(app.allocated_budget) &&
        app.allocated_budget > 0,
    );
    const pool = activeApps.reduce((sum, app) => sum + (app.allocated_budget ?? 0), 0);
    const activeAppIds = new Set(activeApps.map((app) => app.application_id));
    let assignedInPool = 0;
    let assignedKnown = 0;
    let hasAmount = false;
    for (const key of visibleApiKeys) {
      if (key.is_revoked || key.is_active === false) continue;
      if (key.allocated_budget == null || !Number.isFinite(key.allocated_budget)) continue;
      hasAmount = true;
      assignedKnown += key.allocated_budget;
      if (key.application_id && activeAppIds.has(key.application_id)) {
        assignedInPool += key.allocated_budget;
      }
    }
    const comparable = pool > 0;
    const allocatedPct = comparable ? (assignedInPool / pool) * 100 : null;
    return {
      keyCount: visibleApiKeys.length,
      comparable,
      allocatedPct,
      availablePct: allocatedPct == null ? null : Math.max(0, 100 - allocatedPct),
      pool,
      allocatedAmount: hasAmount ? (comparable ? assignedInPool : assignedKnown) : null,
    };
  }, [applications, visibleApiKeys]);

  const formatKeyId = (key: ApiKeyTableRow) => key.api_key ?? "—";

  const formatBudgetPct = (key: ApiKeyTableRow): string => {
    if (key.is_revoked || key.is_active === false) return "—";
    if (key.allocated_percentage == null) return "No ceiling";
    const rounded = Math.round(key.allocated_percentage * 100) / 100;
    return `${rounded % 1 === 0 ? rounded.toFixed(0) : rounded.toFixed(2)}%`;
  };

  return {
    allApiKeys,
    allocationOverview,
    visibleApiKeysCount: visibleApiKeys.length,
    isLoadingAllApiKeys,
    permissions,
    applications: applicationFilterOptions,
    formatPermission,
    visiblePermissionsForKey,
    formatKeyId,
    formatBudgetPct,
    filterApplication,
    setFilterApplication,
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
    revokeBudget,
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
    keyToRotate,
    isRotating,
    rotatedKey,
    handleOpenRotateModal,
    handleCloseRotateModal,
    handleRotateApiKey,
    handleCloseRotatedKey,
    keyToStopPrevious,
    isStoppingPrevious,
    handleOpenStopPreviousModal,
    handleCloseStopPreviousModal,
    handleStopPreviousKeyValue,
    rotateGraceDays,
    setRotateGraceDays,
    isRotateGraceDaysValid: rotateGraceDaysValue !== null,
    defaultGraceDays,
    keyToExtend,
    extendOption,
    setExtendOption,
    extendCustomUntil,
    setExtendCustomUntil,
    extendNewEnd,
    extendError,
    isExtending,
    handleOpenExtendModal,
    handleCloseExtendModal,
    handleExtendPreviousKeyValue,
    keyToRevokeCurrent,
    isRevokingCurrent,
    handleOpenRevokeCurrentModal,
    handleCloseRevokeCurrentModal,
    handleRevokeCurrentKeyValue,
    /** Current value still works: not revoked on its own. */
    isCurrentKeyLive: (key: APIKeyResponse) => !key.api_key_revoked_at,
    isRotationInProgress,
    /** Rotatable when effectively active and its previous value (if any) has stopped working. */
    isKeyRotatable: (key: APIKeyResponse) =>
      isApiKeyEffectivelyActive(key, apiKeyAccessContext) && !isRotationInProgress(key),
  };
}
