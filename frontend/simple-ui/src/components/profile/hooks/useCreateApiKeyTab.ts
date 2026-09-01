import { useState, useEffect, useMemo, useCallback } from "react";
import { showError } from "../../../utils/errorHandler";
import { showToast } from "../../../utils/toast";
import { INSTITUTION } from "../../../config/constants";
import authService from "../../../services/authService";
import { listApplications } from "../../../services/applicationService";
import {
  createScopedApiKey,
  getApiKeyErrorCode,
  listGroupedApiKeys,
} from "../../../services/apiKeyService";
import type { Application } from "../../../types/application";
import type { Permission } from "../../../types/auth";
import { useInferenceTypes } from "../../../hooks/useInferenceTypes";
import { formatSpendMoney } from "../../../utils/usageSpendHelpers";

export interface UseCreateApiKeyTabOptions {
  tenantId?: string | null;
  onApiKeyCreated?: () => void;
}

function formatPct(value: number | null | undefined): string {
  if (value == null) return "";
  const rounded = Math.round(value * 100) / 100;
  return `${rounded % 1 === 0 ? rounded.toFixed(0) : rounded.toFixed(2)}`;
}

export function useCreateApiKeyTab({
  tenantId,
  onApiKeyCreated,
}: UseCreateApiKeyTabOptions) {
  const { taskTypeNames, inferenceTypes } = useInferenceTypes();
  const [allPermissions, setAllPermissions] = useState<Permission[]>([]);
  const [isLoadingPermissions, setIsLoadingPermissions] = useState(false);
  const [applications, setApplications] = useState<Application[]>([]);
  const [isLoadingApplications, setIsLoadingApplications] = useState(false);
  const [availablePct, setAvailablePct] = useState(100);
  const [formBannerError, setFormBannerError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{
    application_id?: string;
    budget?: string;
  }>({});

  const permissions = useMemo(() => {
    if (taskTypeNames.length === 0) return allPermissions;
    const enabled = new Set(taskTypeNames.map((t) => t.trim().toLowerCase()));
    const knownTaskTypes = new Set(
      inferenceTypes.map((t) => t.name.trim().toLowerCase()),
    );
    return allPermissions.filter((p) => {
      const prefix = p.name.split(".")[0]?.toLowerCase() ?? "";
      return knownTaskTypes.has(prefix) ? enabled.has(prefix) : true;
    });
  }, [allPermissions, taskTypeNames, inferenceTypes]);

  const [apiKeyForm, setApiKeyForm] = useState<{
    key_name: string;
    application_id: string;
    allocated_percentage: string;
    expires_days: number | "";
  }>({
    key_name: "",
    application_id: "",
    allocated_percentage: "",
    expires_days: 30,
  });
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [createdApiKeyToken, setCreatedApiKeyToken] = useState<string | null>(
    null,
  );

  const selectedApplication = useMemo(
    () =>
      applications.find((a) => a.application_id === apiKeyForm.application_id) ??
      null,
    [applications, apiKeyForm.application_id],
  );

  const budgetPreview = useMemo(() => {
    const raw = apiKeyForm.allocated_percentage.trim();
    if (!raw || !selectedApplication?.allocated_budget) return null;
    const pct = Number(raw);
    if (!Number.isFinite(pct)) return null;
    const amount = Math.round((pct / 100) * selectedApplication.allocated_budget);
    return formatSpendMoney(amount, "INR");
  }, [apiKeyForm.allocated_percentage, selectedApplication]);

  const refreshAvailablePct = useCallback(
    async (applicationId: string) => {
      if (!applicationId) {
        setAvailablePct(100);
        return;
      }
      if (!tenantId) return;
      try {
        const grouped = await listGroupedApiKeys(tenantId, {
          application_id: applicationId,
        });
        const keys = grouped.groups.flatMap((g) => g.api_keys);
        const used = keys
          .filter((k) => k.is_active !== false && k.is_revoked !== true)
          .reduce((sum, k) => sum + (k.allocated_percentage ?? 0), 0);
        setAvailablePct(Math.max(0, 100 - used));
      } catch {
        setAvailablePct(100);
      }
    },
    [tenantId],
  );

  const handleLoadPermissions = async () => {
    setIsLoadingPermissions(true);
    try {
      const fetchedPermissions = await authService.getAllPermissions();
      setAllPermissions(Array.isArray(fetchedPermissions) ? fetchedPermissions : []);
    } catch (error) {
      showError(error);
    } finally {
      setIsLoadingPermissions(false);
    }
  };

  const handleLoadApplications = async () => {
    const id = tenantId?.trim();
    if (!id) {
      setApplications([]);
      return;
    }
    setIsLoadingApplications(true);
    try {
      const result = await listApplications(id);
      setApplications(result.applications.filter((a) => a.status === "ACTIVE"));
    } catch (error) {
      showError(error);
      setApplications([]);
    } finally {
      setIsLoadingApplications(false);
    }
  };

  useEffect(() => {
    handleLoadPermissions();
    handleLoadApplications();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId]);

  useEffect(() => {
    void refreshAvailablePct(apiKeyForm.application_id);
  }, [apiKeyForm.application_id, refreshAvailablePct]);

  const handleCreateApiKey = async () => {
    setFormBannerError(null);
    setFieldErrors({});

    if (!apiKeyForm.key_name.trim()) {
      showToast({ type: "error", message: "Please enter a key name" });
      return;
    }
    if (!apiKeyForm.application_id) {
      setFieldErrors((prev) => ({
        ...prev,
        application_id: "Select an Application.",
      }));
      return;
    }
    if (selectedPermissions.length === 0) {
      showToast({
        type: "error",
        message: "Please select at least one permission",
      });
      return;
    }
    if (
      apiKeyForm.expires_days === "" ||
      apiKeyForm.expires_days < 1 ||
      apiKeyForm.expires_days > 365
    ) {
      showToast({
        type: "error",
        message: "Please enter a valid expiry (days) between 1 and 365",
      });
      return;
    }

    const rawBudget = apiKeyForm.allocated_percentage.trim();
    if (!rawBudget) {
      setFieldErrors((prev) => ({
        ...prev,
        budget: "Enter a budget allocation percentage.",
      }));
      return;
    }
    const pct = Number(rawBudget);
    if (!Number.isFinite(pct) || pct < 0) {
      setFieldErrors((prev) => ({
        ...prev,
        budget: "Budget can't be negative.",
      }));
      return;
    }
    if (pct > availablePct + 1e-6) {
      setFieldErrors((prev) => ({
        ...prev,
        budget: `Budget can't exceed ${formatPct(availablePct)}% — that's all that's unallocated within this Application.`,
      }));
      return;
    }
    const allocatedPct = pct;

    const tid = tenantId?.trim();
    if (!tid) {
      showToast({ type: "error", message: "Institution context is missing." });
      return;
    }

    setIsCreating(true);
    try {
      const createdKey = await createScopedApiKey(tid, {
        key_name: apiKeyForm.key_name.trim(),
        permissions: selectedPermissions,
        expires_days: Number(apiKeyForm.expires_days) || 30,
        application_id: apiKeyForm.application_id,
        allocated_percentage: allocatedPct,
      });
      onApiKeyCreated?.();
      if (createdKey.api_key) {
        setCreatedApiKeyToken(createdKey.api_key);
      }
      showToast({
        type: "success",
        message: `API key "${createdKey.key_name}" was created. Copy it now — it won't be shown again.`,
      });
      setApiKeyForm({
        key_name: "",
        application_id: "",
        allocated_percentage: "",
        expires_days: 30,
      });
      setSelectedPermissions([]);
      await handleLoadApplications();
    } catch (error) {
      const code = getApiKeyErrorCode(error);
      const detail = (
        error as {
          response?: {
            data?: { detail?: unknown; code?: string; message?: string };
          };
        }
      )?.response?.data;
      const nested =
        typeof detail?.detail === "object" && detail?.detail !== null
          ? (detail.detail as { code?: string; message?: string; error?: string })
          : null;
      const rawMessage =
        nested?.message ??
        (typeof detail?.detail === "string" ? detail.detail : undefined) ??
        detail?.message ??
        "";

      if (code === "APPLICATION_NOT_FOUND") {
        setFieldErrors((prev) => ({
          ...prev,
          application_id: "Application not found or not in scope.",
        }));
        return;
      }
      if (code === "ALLOCATION_TOTAL_EXCEEDED") {
        setFormBannerError(
          nested?.message ??
            rawMessage ??
            "Key allocations would exceed 100% of this Application's Budget.",
        );
        return;
      }

      const legacyCode = nested?.code ?? detail?.code;
      if (
        legacyCode === "NO_ACTIVE_TIER" ||
        /no active tier assignment/i.test(String(rawMessage)) ||
        /tier not assigned/i.test(String(rawMessage))
      ) {
        showToast({
          type: "error",
          message:
            `API key cannot be created: no tier is assigned to this ${INSTITUTION.toLowerCase()}. Assign a tier that has at least one service mapped, then try again.`,
        });
      } else {
        showError(error);
      }
    } finally {
      setIsCreating(false);
    }
  };

  return {
    permissions,
    applications,
    isLoadingPermissions,
    isLoadingApplications,
    apiKeyForm,
    setApiKeyForm,
    selectedPermissions,
    setSelectedPermissions,
    isCreating,
    createdApiKeyToken,
    clearCreatedApiKeyToken: () => setCreatedApiKeyToken(null),
    handleCreateApiKey,
    selectedApplication,
    budgetPreview,
    availablePct,
    formBannerError,
    fieldErrors,
    formatAvailablePct: () => formatPct(availablePct),
  };
}
