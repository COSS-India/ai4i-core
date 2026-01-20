/**
 * Hook for checking and handling session expiry (24 hours)
 */
import { useCallback } from 'react';
import { useRouter } from 'next/router';
import { useToast } from '@chakra-ui/react';
import authService from '../services/authService';

export const useSessionExpiry = () => {
  const router = useRouter();
  const toast = useToast();

  /**
   * Check if session has expired and handle accordingly
   * @returns true if session is valid, false if expired or not authenticated
   */
  const checkSessionExpiry = useCallback((): boolean => {
    // Check if user is authenticated first
    if (!authService.isAuthenticated()) {
      // No token found - user is not authenticated
      authService.clearAuthTokens();
      authService.clearStoredUser();

      // Show toast notification
      toast({
        title: 'Session  Expired',
        description: 'Please log in to continue.',
        status: 'warning',
        duration: 5000,
        isClosable: true,
        position: 'top',
      });

      // Redirect to login page
      router.push('/auth');
      
      return false;
    }

    // Check if session has expired (24 hours)
    if (authService.isSessionExpired()) {
      // Clear tokens and user data
      authService.clearAuthTokens();
      authService.clearStoredUser();

      // Show toast notification
      toast({
        title: 'Session Expired',
        description: 'Your session has expired after 24 hours. Please log in again.',
        status: 'warning',
        duration: 5000,
        isClosable: true,
        position: 'top',
      });

      // Redirect to login page
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



