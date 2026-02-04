/**
 * Hook for checking and handling session expiry
 * - 7 days if remember_me is true
 * - 24 hours if remember_me is false
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

    // Check if session has expired (24 hours or 7 days depending on remember_me)
    if (authService.isSessionExpired()) {
      // Clear tokens and user data
      authService.clearAuthTokens();
      authService.clearStoredUser();

      // Get remember_me setting for appropriate message
      const rememberMe = typeof window !== 'undefined' 
        ? localStorage.getItem('remember_me') === 'true' 
        : false;
      const sessionDuration = rememberMe ? '7 days' : '24 hours';

      // Show toast notification
      toast({
        title: 'Session Expired',
        description: `Your session has expired after ${sessionDuration}. Please log in again.`,
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



