import { useState } from "react";
import { useToastWithDeduplication } from "../../../hooks/useToastWithDeduplication";
import authService from "../../../services/authService";
import type { User } from "../../../types/auth";

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
  const [permissions, setPermissions] = useState<string[]>([]);
  const [selectedUserForPermissions, setSelectedUserForPermissions] =
    useState<SelectedUserForPermissions | null>(null);
  const [selectedUserPermissions, setSelectedUserPermissions] = useState<string[]>([]);
  const [isLoadingPermissions, setIsLoadingPermissions] = useState(false);
  const [apiKeyForUser, setApiKeyForUser] = useState({
    key_name: "",
    permissions: [] as string[],
    expires_days: 30,
  });
  const [selectedPermissionsForUser, setSelectedPermissionsForUser] = useState<string[]>([]);
  const [isCreatingApiKeyForUser, setIsCreatingApiKeyForUser] = useState(false);

  const handleLoadPermissions = async () => {
    setIsLoadingPermissions(true);
    try {
      const allPermissions = await authService.getAllPermissions();
      setPermissions(allPermissions);
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
    setIsCreatingApiKeyForUser(true);
    try {
      const createdKey = await authService.createApiKeyForUser({
        key_name: apiKeyForUser.key_name,
        permissions: selectedPermissionsForUser,
        expires_days: apiKeyForUser.expires_days,
        user_id: selectedUserForPermissions.id,
      });
      try {
        const listResponse = await authService.listApiKeys();
        setApiKeys(Array.isArray(listResponse.api_keys) ? listResponse.api_keys : []);
        setSelectedApiKeyId(listResponse.selected_api_key_id ?? null);
      } catch (err) {
        console.error("Failed to refresh API keys list:", err);
      }
      toast({
        title: "API Key Created",
        description: `API key "${createdKey.key_name}" created successfully for ${selectedUserForPermissions.username}.`,
        status: "success",
        duration: 5000,
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
    handleLoadPermissions,
    handleUserSelect,
    handleCreateApiKeyForUser,
  };
}
