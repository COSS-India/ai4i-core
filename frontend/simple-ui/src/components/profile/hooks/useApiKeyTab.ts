import { useState } from "react";
import { useToast } from "@chakra-ui/react";
import authService from "../../../services/authService";
import type { APIKeyResponse } from "../../../types/auth";

export interface UseApiKeyTabOptions {
  getApiKey: () => string | null | undefined;
  setApiKey: (key: string) => void;
  setSelectedApiKeyId: (id: number | null) => void;
  checkSessionExpiry: () => boolean;
}

export function useApiKeyTab({
  getApiKey,
  setApiKey,
  setSelectedApiKeyId,
  checkSessionExpiry,
}: UseApiKeyTabOptions) {
  const toast = useToast();
  const [showApiKey, setShowApiKey] = useState(false);

  const handleCopyApiKey = () => {
    if (!checkSessionExpiry()) return;
    const key = getApiKey();
    if (key) {
      navigator.clipboard.writeText(key);
      toast({
        title: "API Key Copied",
        description: "API key has been copied to clipboard",
        status: "success",
        duration: 2000,
        isClosable: true,
      });
    }
  };

  const handleSelectApiKey = async (key: APIKeyResponse) => {
    try {
      await authService.selectApiKey(key.id);
      setSelectedApiKeyId(key.id);
      if (key.key_value) {
        setApiKey(key.key_value);
      }
      toast({
        title: "API Key Selected",
        description: key.key_value
          ? `API key "${key.key_name}" has been set as your current key`
          : `API key "${key.key_name}" is now selected. Key value is not available (only shown once on creation).`,
        status: key.key_value ? "success" : "info",
        duration: key.key_value ? 3000 : 4000,
        isClosable: true,
      });
    } catch (err) {
      toast({
        title: "Error",
        description: err instanceof Error ? err.message : "Failed to save selected API key",
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    }
  };

  return {
    showApiKey,
    setShowApiKey,
    handleCopyApiKey,
    handleSelectApiKey,
  };
}
