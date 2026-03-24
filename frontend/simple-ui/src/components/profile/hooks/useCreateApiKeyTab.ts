import { useState } from "react";
import { useToastWithDeduplication } from "../../../hooks/useToastWithDeduplication";
import authService from "../../../services/authService";
import type { User, Permission } from "../../../types/auth";

export interface UseCreateApiKeyTabOptions {
  users: User[];
  isLoadingUsers: boolean;
  setApiKeys: (keys: import("../../../types/auth").APIKeyResponse[]) => void;
  setSelectedApiKeyId: (id: number | null) => void;
}

export interface SelectedUserForPermissions {
  id: number;
  email: string;
  username: string;
}

export function useCreateApiKeyTab({
  users,
  setApiKeys,
  setSelectedApiKeyId,
}: UseCreateApiKeyTabOptions) {
  const toast = useToastWithDeduplication();
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [selectedUserForPermissions, setSelectedUserForPermissions] =
    useState<SelectedUserForPermissions | null>(null);
  const [selectedUserPermissions, setSelectedUserPermissions] = useState<string[]>([]);
  const [isLoadingPermissions, setIsLoadingPermissions] = useState(false);
  const [apiKeyForUser, setApiKeyForUser] = useState<{
    key_name: string;
    permissions: string[];
    expires_days: number | "";
  }>({
    key_name: "",
    permissions: [],
    expires_days: 30,
  });
  const [selectedPermissionsForUser, setSelectedPermissionsForUser] = useState<string[]>([]);
  const [isCreatingApiKeyForUser, setIsCreatingApiKeyForUser] = useState(false);
  const [createdApiKeyToken, setCreatedApiKeyToken] = useState<string | null>(null);

  const handleLoadPermissions = async () => {
    setIsLoadingPermissions(true);
    try {
      const allPermissions = await authService.getAllPermissions();
      setPermissions(Array.isArray(allPermissions) ? allPermissions : []);
      toast({
        title: "Permissions Loaded",
        description: `Loaded ${allPermissions.length} permissions`,
        status: "success",
        duration: 2000,
        isClosable: true,
      });
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

  const handleUserSelect = (userId: number) => {
    const u = users.find((x) => x.id === userId);
    if (u) {
      setSelectedUserForPermissions({
        id: u.id,
        email: u.email,
        username: u.username || "",
      });
      setSelectedUserPermissions([]);
    } else {
      setSelectedUserForPermissions(null);
      setSelectedUserPermissions([]);
    }
  };

  const handleCreateApiKeyForUser = async () => {
    if (!selectedUserForPermissions) return;
    if (!apiKeyForUser.key_name.trim()) {
      toast({
        title: "Validation Error",
        description: "Please enter a key name",
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    if (selectedPermissionsForUser.length === 0) {
      toast({
        title: "Validation Error",
        description: "Please select at least one permission",
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    if (apiKeyForUser.expires_days === "" || apiKeyForUser.expires_days < 1 || apiKeyForUser.expires_days > 365) {
      toast({
        title: "Validation Error",
        description: "Please enter a valid expiry (days) between 1 and 365",
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    setIsCreatingApiKeyForUser(true);
    try {
      // Convert selected permission names to IDs for the v2 API
      const permissionIds = selectedPermissionsForUser
        .map((name) => permissions.find((p) => p.name === name)?.id)
        .filter((id): id is number => id != null);
      const createdKey = await authService.createApiKeyForUser({
        key_name: apiKeyForUser.key_name,
        permissions: permissionIds,
        expires_days: Number(apiKeyForUser.expires_days) || 30,
        user_id: selectedUserForPermissions.id,
      });
      try {
        const listResponse = await authService.listApiKeys();
        setApiKeys(Array.isArray(listResponse.api_keys) ? listResponse.api_keys : []);
      } catch (err) {
        console.error("Failed to refresh API keys list:", err);
      }
      // Store the JWT token so the UI can display it for copying
      if (createdKey.api_key) {
        setCreatedApiKeyToken(createdKey.api_key);
      }
      toast({
        title: "API Key Created",
        description: `API key "${createdKey.key_name}" created successfully for ${selectedUserForPermissions.username}. Copy it now — it won't be shown again.`,
        status: "success",
        duration: 8000,
        isClosable: true,
      });
      setApiKeyForUser({ key_name: "", permissions: [], expires_days: 30 });
      setSelectedPermissionsForUser([]);
    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to create API key",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsCreatingApiKeyForUser(false);
    }
  };

  return {
    permissions,
    selectedUserForPermissions,
    selectedUserPermissions,
    isLoadingPermissions,
    apiKeyForUser,
    setApiKeyForUser,
    selectedPermissionsForUser,
    setSelectedPermissionsForUser,
    isCreatingApiKeyForUser,
    createdApiKeyToken,
    clearCreatedApiKeyToken: () => setCreatedApiKeyToken(null),
    handleLoadPermissions,
    handleUserSelect,
    handleCreateApiKeyForUser,
  };
}
