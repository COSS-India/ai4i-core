import { useState, useEffect, useMemo } from "react";
import { showError } from "../../../utils/errorHandler";
import { showToast } from "../../../utils/toast";
import authService from "../../../services/authService";
import type { Permission } from "../../../types/auth";
import { useInferenceTypes } from "../../../hooks/useInferenceTypes";

export interface UseCreateApiKeyTabOptions {
  onApiKeyCreated?: () => void;
}

export function useCreateApiKeyTab({
  onApiKeyCreated,
}: UseCreateApiKeyTabOptions) {
  const { taskTypeNames, inferenceTypes } = useInferenceTypes();
  const [allPermissions, setAllPermissions] = useState<Permission[]>([]);
  const [isLoadingPermissions, setIsLoadingPermissions] = useState(false);

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
    expires_days: number | "";
  }>({
    key_name: "",
    expires_days: 30,
  });
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [createdApiKeyToken, setCreatedApiKeyToken] = useState<string | null>(
    null,
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

  useEffect(() => {
    handleLoadPermissions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreateApiKey = async () => {
    if (!apiKeyForm.key_name.trim()) {
      showToast({ type: "error", message: "Please enter a key name" });
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
    setIsCreating(true);
    try {
      const createdKey = await authService.createApiKey({
        key_name: apiKeyForm.key_name.trim(),
        permissions: selectedPermissions,
        expires_days: Number(apiKeyForm.expires_days) || 30,
      });
      onApiKeyCreated?.();
      if (createdKey.api_key) {
        setCreatedApiKeyToken(createdKey.api_key);
      }
      showToast({
        type: "success",
        message: `API key "${createdKey.key_name}" was created. Copy it now — it won't be shown again.`,
      });
      setApiKeyForm({ key_name: "", expires_days: 30 });
      setSelectedPermissions([]);
    } catch (error) {
      showError(error);
    } finally {
      setIsCreating(false);
    }
  };

  return {
    permissions,
    isLoadingPermissions,
    apiKeyForm,
    setApiKeyForm,
    selectedPermissions,
    setSelectedPermissions,
    isCreating,
    createdApiKeyToken,
    clearCreatedApiKeyToken: () => setCreatedApiKeyToken(null),
    handleCreateApiKey,
  };
}
