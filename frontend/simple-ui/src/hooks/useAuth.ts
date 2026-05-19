/**
 * Authentication hook
 */
import { useState, useEffect, useCallback } from 'react';
import { User, AuthState, LoginRequest, LoginResponse, RegisterRequest } from '../types/auth';
import authService from '../services/authService';
import { useTokenRefresh } from './useTokenRefresh';

// Broadcast auth state changes so other hook instances (e.g., Header) can react immediately
const AUTH_UPDATED_EVENT = 'auth:updated';

/**
 * Cross-tab logout signal. Kept in localStorage (not sessionStorage) because only
 * `storage` events for localStorage fire across tabs.
 */
const AUTH_SESSION_REVOKED_STORAGE_KEY = 'ai4i:auth:session-revoked';

// Shared init promise: only one getCurrentUser() + listApiKeys() run for all useAuth() instances.
// This prevents N components (Header, Sidebar, AuthGuard, pages, useFeatureFlag hooks) from each
// calling auth/me and listApiKeys on every load.
let authInitPromise: Promise<void> | null = null;

function runAuthInitOnce(): Promise<void> {
  if (authInitPromise !== null) return authInitPromise;
  authInitPromise = (async () => {
    const storedUser = authService.getStoredUser();
    const hasToken = authService.isAuthenticated();

    if (hasToken && storedUser) {
      try {
        const currentUser = await authService.getCurrentUser();
        authService.setStoredUser(currentUser);
      } catch (error: any) {
        const errorMessage = error?.message || 'Token validation failed';
        if (errorMessage.includes('timeout') || errorMessage.includes('Timeout')) {
          console.warn('Auth service timeout during initialization - clearing auth state silently');
        }
        authService.clearAuthTokens();
        authService.clearStoredUser();
        authInitPromise = null; // Allow re-init after next login in same session
      }
    } else {
      if (!hasToken) authService.clearStoredUser();
    }
  })();
  return authInitPromise;
}

// Reset shared init so that after logout a future load can run init again (e.g. new login).
export function resetAuthInitPromise(): void {
  authInitPromise = null;
}

/**
 * End the session in this browser only: clear tokens and stored user, do not call the auth logout API.
 * Other tabs receive a localStorage `storage` event and sign out as well.
 */
export function forceFrontendSessionEnd(): void {
  if (typeof window === 'undefined') return;
  authService.clearAuthTokens();
  authService.clearStoredUser();
  resetAuthInitPromise();
  window.dispatchEvent(new CustomEvent(AUTH_UPDATED_EVENT));
  try {
    localStorage.setItem(AUTH_SESSION_REVOKED_STORAGE_KEY, String(Date.now()));
  } catch {
    // private mode / blocked storage — still redirect below
  }
  window.location.assign('/auth');
}

export const useAuth = () => {
  const [authState, setAuthState] = useState<AuthState>({
    user: null,
    accessToken: null,
    refreshToken: null,
    isAuthenticated: false,
    isLoading: true,
    isLoginLoading: false,
    isGuestLoginLoading: false,
    error: null,
  });

  // Enable automatic token refresh when user is authenticated
  useTokenRefresh({
    enableBackgroundRefresh: authState.isAuthenticated,
    refreshInterval: 300000, // Check every 5 minutes
    refreshThresholdMinutes: 5, // Refresh if token expires within 5 minutes
  });

  // Initialize auth state (shared init: only one auth/me + listApiKeys for all hook instances)
  useEffect(() => {
    const handleAuthUpdated = () => {
      try {
        const storedUser = authService.getStoredUser();
        const hasToken = authService.isAuthenticated();
        setAuthState(prev => ({
          ...prev,
          user: storedUser,
          accessToken: authService.getAccessToken(),
          refreshToken: authService.getRefreshToken(),
          isAuthenticated: !!hasToken && !!storedUser,
          isLoading: false,
          isLoginLoading: false,
          isGuestLoginLoading: false,
          error: null,
        }));
      } catch {
        // noop
      }
    };

    // Listen for cross-component auth updates (login/logout from another component)
    if (typeof window !== 'undefined') {
      window.addEventListener(AUTH_UPDATED_EVENT, handleAuthUpdated as EventListener);
    }

    const syncStateFromAuthService = () => {
      const storedUser = authService.getStoredUser();
      const hasToken = authService.isAuthenticated();
      setAuthState({
        user: storedUser,
        accessToken: authService.getAccessToken(),
        refreshToken: authService.getRefreshToken(),
        isAuthenticated: !!hasToken && !!storedUser,
        isLoading: false,
        isLoginLoading: false,
        isGuestLoginLoading: false,
        error: null,
      });
    };

    const initializeAuth = async () => {
      try {
        await runAuthInitOnce();
        syncStateFromAuthService();
      } catch (error) {
        console.error('Auth initialization failed:', error);
        authService.clearAuthTokens();
        authService.clearStoredUser();
        syncStateFromAuthService();
      }
    };

    const handleSessionRevokedFromStorage = (event: StorageEvent) => {
      if (event.key !== AUTH_SESSION_REVOKED_STORAGE_KEY || event.newValue == null) return;
      authService.clearAuthTokens();
      authService.clearStoredUser();
      resetAuthInitPromise();
      setAuthState({
        user: null,
        accessToken: null,
        refreshToken: null,
        isAuthenticated: false,
        isLoading: false,
        isLoginLoading: false,
        isGuestLoginLoading: false,
        error: null,
      });
      window.dispatchEvent(new CustomEvent(AUTH_UPDATED_EVENT));
      const path = window.location?.pathname ?? '';
      if (!path.startsWith('/auth')) {
        window.location.assign('/auth');
      }
    };

    initializeAuth();
    if (typeof window !== 'undefined') {
      window.addEventListener('storage', handleSessionRevokedFromStorage);
    }
    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener(AUTH_UPDATED_EVENT, handleAuthUpdated as EventListener);
        window.removeEventListener('storage', handleSessionRevokedFromStorage);
      }
    };
  }, []);

  const completeLogin = useCallback(async (response: LoginResponse) => {
    // Verify tokens are stored before proceeding
    const accessToken = authService.getAccessToken();
    if (!accessToken) {
      throw new Error('Access token was not stored after login. Please try again.');
    }

    // Small delay to ensure tokens are fully stored (especially for sessionStorage)
    await new Promise(resolve => setTimeout(resolve, 100));

    // Use /me endpoint to validate token and get user data in one call
    try {
      const user = await authService.getCurrentUser();

      // Store user data and tokens immediately before state update
      authService.setStoredUser(user);
      if (!authService.getAccessToken() || !authService.getRefreshToken()) {
        console.warn('useAuth: Tokens not found in storage after login');
      }

      setAuthState({
        user,
        accessToken: response.access_token,
        refreshToken: response.refresh_token,
        isAuthenticated: true,
        isLoading: false,
        isLoginLoading: false,
        isGuestLoginLoading: false,
        error: null,
      });

      // Notify other components/hooks to refresh their view immediately
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent(AUTH_UPDATED_EVENT));
      }

      return response;
    } catch (meError) {
      console.error('useAuth: Failed to fetch user data / token validation failed:', meError);
      const errorMessage = meError instanceof Error ? meError.message : 'Token validation failed';
      console.error('useAuth: Error details:', {
        message: errorMessage,
        hasToken: !!authService.getAccessToken(),
        tokenLength: authService.getAccessToken()?.length || 0,
      });

      // Clear tokens if /me fails (token is invalid or expired)
      authService.clearAuthTokens();
      setAuthState(prev => ({
        ...prev,
        isLoading: false,
        isLoginLoading: false,
        isGuestLoginLoading: false,
        error: errorMessage.includes('timeout')
          ? 'Request timeout. The server is taking too long to respond. Please try again.'
          : errorMessage.includes('401') || errorMessage.includes('Unauthorized')
          ? 'Invalid credentials. Please check your username and password.'
          : `Token validation failed: ${errorMessage}. Please try logging in again.`,
      }));
      throw new Error(errorMessage);
    }
  }, []);

  const login = useCallback(async (credentials: LoginRequest) => {
    setAuthState(prev => ({ ...prev, isLoading: true, isLoginLoading: true, isGuestLoginLoading: false, error: null }));

    try {
      const response = await authService.login(credentials);
      return completeLogin(response);
    } catch (error) {
      console.error('useAuth: Login failed:', error);
      let errorMessage = error instanceof Error ? error.message : 'Login failed';
      
      // Provide more user-friendly error messages
      if (errorMessage.includes('401') || errorMessage.includes('Unauthorized')) {
        errorMessage = 'Invalid email or password. Please check your credentials and try again.';
      } else if (errorMessage.includes('403') || errorMessage.includes('Forbidden')) {
        errorMessage = 'Access denied. Your account may be inactive. Please contact support.';
      } else if (errorMessage.includes('404') || errorMessage.includes('Not Found')) {
        errorMessage = 'Login endpoint not found. Please check your connection and try again.';
      } else if (errorMessage.includes('timeout') || errorMessage.includes('Timeout')) {
        errorMessage = 'Request timeout. The server is taking too long to respond. Please try again.';
      } else if (errorMessage.includes('NetworkError') || errorMessage.includes('Failed to fetch')) {
        errorMessage = 'Network error. Please check your internet connection and try again.';
      }
      
      setAuthState(prev => ({
        ...prev,
        isLoading: false,
        isLoginLoading: false,
        isGuestLoginLoading: false,
        error: errorMessage,
      }));
      throw new Error(errorMessage);
    }
  }, [completeLogin]);

  const guestLogin = useCallback(async () => {
    setAuthState(prev => ({ ...prev, isLoading: true, isLoginLoading: false, isGuestLoginLoading: true, error: null }));

    try {
      const response = await authService.guestLogin();
      return await completeLogin(response);
    } catch (error) {
      console.error('useAuth: Guest login failed:', error);
      const errorMessage = error instanceof Error ? error.message : 'Guest login failed';
      setAuthState(prev => ({
        ...prev,
        isLoading: false,
        isLoginLoading: false,
        isGuestLoginLoading: false,
        error: errorMessage,
      }));
      throw new Error(errorMessage);
    }
  }, [completeLogin]);

  const register = useCallback(async (userData: RegisterRequest) => {
    setAuthState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      const user = await authService.register(userData);
      
      setAuthState(prev => ({
        ...prev,
        isLoading: false,
        error: null,
      }));

      return user;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Registration failed';
      setAuthState(prev => ({
        ...prev,
        isLoading: false,
        error: errorMessage,
      }));
      throw error;
    }
  }, []);

  const logout = useCallback(async () => {
    setAuthState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      await authService.logout();
      
      setAuthState({
        user: null,
        accessToken: null,
        refreshToken: null,
        isAuthenticated: false,
        isLoading: false,
        isLoginLoading: false,
        isGuestLoginLoading: false,
        error: null,
      });

      // Clear stored user data
      authService.clearStoredUser();
      resetAuthInitPromise();

      // Broadcast auth update so UI reflects logout without manual refresh
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent(AUTH_UPDATED_EVENT));
        // Redirect to main sign in page after logout
        window.location.href = '/';
      }
    } catch (error) {
      console.error('Logout failed:', error);
      // Even if logout fails on server, clear local state
      setAuthState({
        user: null,
        accessToken: null,
        refreshToken: null,
        isAuthenticated: false,
        isLoading: false,
        isLoginLoading: false,
        isGuestLoginLoading: false,
        error: null,
      });
      authService.clearStoredUser();
      resetAuthInitPromise();

      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent(AUTH_UPDATED_EVENT));
        // Redirect to main sign in page after logout
        window.location.href = '/';
      }
    }
  }, []);

  const refreshToken = useCallback(async () => {
    try {
      const response = await authService.refreshToken();
      
      setAuthState(prev => ({
        ...prev,
        accessToken: response.access_token,
        error: null,
      }));

      return response;
    } catch (error) {
      console.error('Token refresh failed:', error);
      // If refresh fails, logout user
      await logout();
      throw error;
    }
  }, [logout]);

  const updateUser = useCallback(async (userData: Partial<User>) => {
    setAuthState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      const updatedUser = await authService.updateCurrentUser(userData);
      
      setAuthState(prev => ({
        ...prev,
        user: updatedUser,
        isLoading: false,
        error: null,
      }));

      // Update stored user data
      authService.setStoredUser(updatedUser);

      return updatedUser;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Update failed';
      setAuthState(prev => ({
        ...prev,
        isLoading: false,
        error: errorMessage,
      }));
      throw error;
    }
  }, []);

  const changePassword = useCallback(async (passwordData: {
    current_password: string;
    new_password: string;
    confirm_password: string;
  }) => {
    setAuthState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      const response = await authService.changePassword(passwordData);
      
      setAuthState(prev => ({
        ...prev,
        isLoading: false,
        error: null,
      }));

      return response;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Password change failed';
      setAuthState(prev => ({
        ...prev,
        isLoading: false,
        error: errorMessage,
      }));
      throw error;
    }
  }, []);

  const clearError = useCallback(() => {
    setAuthState(prev => ({ ...prev, error: null }));
  }, []);

  return {
    ...authState,
    login,
    guestLogin,
    register,
    logout,
    refreshToken,
    updateUser,
    changePassword,
    clearError,
  };
};
