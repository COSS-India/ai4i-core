/**
 * Hook for checking and handling session expiry.
 * Session expiry is enforced via JWT exp + refresh tokens (server-side);
 * no client-stored timestamp is used.
 */
import { useCallback } from 'react';
import { useRouter } from 'next/router';
import { useToastWithDeduplication } from './useToastWithDeduplication';
import authService from '../services/authService';

export const useSessionExpiry = () => {
  const router = useRouter();
  const toast = useToastWithDeduplication();

  /**
   * Check if session has expired and handle accordingly.
   * Uses JWT exp and refresh token presence; server enforces refresh token expiry.
   * @returns true if session is valid, false if expired or not authenticated
   */
  const checkSessionExpiry = useCallback((): boolean => {
    if (!authService.isAuthenticated()) {
      authService.clearAuthTokens();
      authService.clearStoredUser();
      toast({
        title: 'Session expired',
        description: 'Please log in to continue.',
        status: 'warning',
        duration: 5000,
        isClosable: true,
        position: 'top',
      });
      router.push('/auth');
      return false;
    }

    if (authService.isSessionExpired()) {
      authService.clearAuthTokens();
      authService.clearStoredUser();
      toast({
        title: 'Session expired',
        description: 'Your session has expired. Please sign in again.',
        status: 'warning',
        duration: 5000,
        isClosable: true,
        position: 'top',
      });
      router.push('/auth');
      return false;
    }

    return true;
  }, [router, toast]);

  /**
   * Check session expiry before executing an action
   * @param action - Function to execute if session is valid
   * @returns Result of the action or false if session expired
   */
  const withSessionCheck = useCallback(
    async <T>(action: () => T | Promise<T>): Promise<T | false> => {
      if (!checkSessionExpiry()) {
        return false;
      }
      return await action();
    },
    [checkSessionExpiry]
  );

  return {
    checkSessionExpiry,
    withSessionCheck,
    isSessionExpired: authService.isSessionExpired.bind(authService),
    getTimeUntilSessionExpiry: authService.getTimeUntilSessionExpiry.bind(authService),
  };
};



