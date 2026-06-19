import { useState, useEffect } from "react";
import { useToastWithDeduplication } from "../../../utils/toast";
import authService from "../../../services/authService";
import type { Permission } from "../../../types/auth";
import { cacheCreatedApiKeyHex } from "../../../utils/apiKeyUtils";

export interface UseCreateApiKeyTabOptions {
  onApiKeyCreated?: () => void;
}

export function useCreateApiKeyTab({ onApiKeyCreated }: UseCreateApiKeyTabOptions) {
  const toast = useToastWithDeduplication();
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [isLoadingPermissions, setIsLoadingPermissions] = useState(false);
  const [apiKeyForm, setApiKeyForm] = useState<{
    key_name: string;
    expires_days: number | "";
  }>({
    key_name: "",
    expires_days: 30,
  });
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [createdApiKeyToken, setCreatedApiKeyToken] = useState<string | null>(null);

  const handleLoadPermissions = async () => {
    setIsLoadingPermissions(true);
    try {
      const allPermissions = await authService.getAllPermissions();
      setPermissions(Array.isArray(allPermissions) ? allPermissions : []);
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to load permissions",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
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
      toast({
        title: "Validation Error",
        description: "Please enter a key name",
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    if (selectedPermissions.length === 0) {
      toast({
        title: "Validation Error",
        description: "Please select at least one permission",
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    if (
      apiKeyForm.expires_days === "" ||
      apiKeyForm.expires_days < 1 ||
      apiKeyForm.expires_days > 365
    ) {
      toast({
        title: "Validation Error",
        description: "Please enter a valid expiry (days) between 1 and 365",
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    setIsCreating(true);
    try {
      const permissionIds = selectedPermissions
        .map((name) => permissions.find((p) => p.name === name)?.id)
        .filter((id): id is number => id != null);
      const createdKey = await authService.createApiKey({
        key_name: apiKeyForm.key_name.trim(),
        permissions: permissionIds,
        expires_days: Number(apiKeyForm.expires_days) || 30,
      });
      onApiKeyCreated?.();
      if (createdKey.api_key) {
        setCreatedApiKeyToken(createdKey.api_key);
        cacheCreatedApiKeyHex(
          createdKey.key_name,
          createdKey.api_key,
          createdKey.id ?? createdKey.key_id,
        );
      }
      toast({
        title: "API Key Created",
        description: `API key "${createdKey.key_name}" was created. Copy it now — it won't be shown again.`,
        status: "success",
        duration: 8000,
        isClosable: true,
      });
      setApiKeyForm({ key_name: "", expires_days: 30 });
      setSelectedPermissions([]);
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to create API key",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
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
