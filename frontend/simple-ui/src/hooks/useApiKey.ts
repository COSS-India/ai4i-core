// Custom React hook for API key management with localStorage persistence

import { useState, useEffect } from 'react';

interface UseApiKeyReturn {
  apiKey: string | null;
  isAuthenticated: boolean;
  setApiKey: (key: string) => void;
  clearApiKey: () => void;
  getApiKey: () => string | null;
}

export const useApiKey = (): UseApiKeyReturn => {
  const [apiKey, setApiKeyState] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);

  // Load API key from localStorage (user-provided) or environment variable (fallback) on mount
  useEffect(() => {
    if (typeof window !== 'undefined') {
      // First check localStorage (user-provided via "manage API key")
      const storedApiKey = localStorage.getItem('api_key');
      if (storedApiKey && storedApiKey.trim() !== '') {
        setApiKeyState(storedApiKey);
        setIsAuthenticated(true);
      } else {
        // Fallback to environment variable if no API key is provided
        const envApiKey = process.env.NEXT_PUBLIC_API_KEY;
        if (envApiKey && envApiKey.trim() !== '' && envApiKey !== 'your_api_key_here') {
          // Don't automatically store env key in localStorage - only use it as fallback
          setApiKeyState(envApiKey.trim());
          setIsAuthenticated(true);
        }
      }
    }
  }, []);

  /**
   * Set API key and store in localStorage
   * @param key - API key to set
   */
  const setApiKey = (key: string): void => {
    if (!key || key.trim() === '') {
      throw new Error('API key cannot be empty');
    }

    if (typeof window !== 'undefined') {
      localStorage.setItem('api_key', key);
      setApiKeyState(key);
      setIsAuthenticated(true);
    }
  };

  /**
   * Clear API key from localStorage
   */
  const clearApiKey = (): void => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('api_key');
      setApiKeyState(null);
      setIsAuthenticated(false);
    }
  };

  /**
   * Get current API key
   * Priority: localStorage (user-provided) > env file (fallback)
   * @returns Current API key or null
   */
  const getApiKey = (): string | null => {
    if (typeof window !== 'undefined') {
      // First check localStorage (user-provided via "manage API key")
      const storedApiKey = localStorage.getItem('api_key');
      if (storedApiKey && storedApiKey.trim() !== '') {
        return storedApiKey.trim();
      }
      // Fallback to environment variable if no API key is provided
      const envApiKey = process.env.NEXT_PUBLIC_API_KEY;
      if (envApiKey && envApiKey.trim() !== '' && envApiKey !== 'your_api_key_here') {
        return envApiKey.trim();
      }
    }
    return apiKey;
  };

  return {
    apiKey,
    isAuthenticated,
    setApiKey,
    clearApiKey,
    getApiKey,
  };
};