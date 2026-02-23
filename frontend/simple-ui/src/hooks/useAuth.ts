/**
 * Authentication hook
 */
import { useState, useEffect, useCallback } from 'react';
import { User, AuthState, LoginRequest, RegisterRequest } from '../types/auth';
import authService from '../services/authService';
import { useTokenRefresh } from './useTokenRefresh';

// Broadcast auth state changes so other hook instances (e.g., Header) can react immediately
const AUTH_UPDATED_EVENT = 'auth:updated';

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
        try {
          const apiKeyList = await authService.listApiKeys();
          authService.applyApiKeyListToStorage(apiKeyList);
        } catch {
          // Non-blocking; user can set key in profile
        }
      } catch (error: any) {
        const errorMessage = error?.message || 'Token validation failed';
        console.log('Token validation failed during initialization:', errorMessage);
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

export const useAuth = () => {
  const [authState, setAuthState] = useState<AuthState>({
    user: null,
    accessToken: null,
    refreshToken: null,
    isAuthenticated: false,
    isLoading: true,
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

    initializeAuth();
    return () => {
      if (typeof window !== 'undefined') {
        window.removeEventListener(AUTH_UPDATED_EVENT, handleAuthUpdated as EventListener);
      }
    };
  }, []);

  const login = useCallback(async (credentials: LoginRequest) => {
    setAuthState(prev => ({ ...prev, isLoading: true, error: null }));
    console.log('useAuth: Starting login...');

    try {
      const response = await authService.login(credentials);
      console.log('useAuth: Login API successful, tokens received');
      
      // Verify tokens are stored before proceeding
      const accessToken = authService.getAccessToken();
      const refreshToken = authService.getRefreshToken();
      console.log('useAuth: Token verification:', {
        hasAccessToken: !!accessToken,
        hasRefreshToken: !!refreshToken,
        accessTokenLength: accessToken?.length || 0,
      });
      
      if (!accessToken) {
        throw new Error('Access token was not stored after login. Please try again.');
      }
      
      // Small delay to ensure tokens are fully stored (especially for sessionStorage)
      await new Promise(resolve => setTimeout(resolve, 100));
      
      // Use /me endpoint to validate token and get user data in one call
      // This is more efficient than calling validate then me separately
      console.log('useAuth: Fetching user data from /me endpoint (this also validates the token)...');
      try {
        const user = await authService.getCurrentUser();
        console.log('useAuth: User data fetched successfully, token is valid:', user);

        // Store user data and tokens immediately before state update
        // This ensures all data is in localStorage before React re-renders
        authService.setStoredUser(user);
        // Tokens are already stored by authService.login(), but ensure they're there
        if (!authService.getAccessToken() || !authService.getRefreshToken()) {
          // This shouldn't happen, but just in case
          console.warn('useAuth: Tokens not found in storage after login');
        }

        // Token is valid and we have user data - authentication successful
        // Use functional update to ensure we get the latest state
        console.log('useAuth: Setting authentication state - isAuthenticated: true');
        setAuthState(prev => {
          const newState = {
            user: user,
            accessToken: response.access_token,
            refreshToken: response.refresh_token,
            isAuthenticated: true,
            isLoading: false,
            error: null,
          };
          console.log('useAuth: Auth state updated:', { 
            isAuthenticated: newState.isAuthenticated, 
            username: newState.user?.username 
          });
          return newState;
        });

        console.log('useAuth: ✅ Authentication complete - user logged in successfully');

        // Fetch API keys and store selected key in localStorage for use in services
        try {
          const apiKeyList = await authService.listApiKeys();
          authService.applyApiKeyListToStorage(apiKeyList);
        } catch (apiKeyErr) {
          console.warn('useAuth: Failed to fetch API keys after login:', apiKeyErr);
        }

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
          error: errorMessage.includes('timeout') 
            ? 'Request timeout. The server is taking too long to respond. Please try again.'
            : errorMessage.includes('401') || errorMessage.includes('Unauthorized')
            ? 'Invalid credentials. Please check your username and password.'
            : `Token validation failed: ${errorMessage}. Please try logging in again.`,
        }));
        throw new Error(errorMessage);
      }
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
        error: errorMessage,
      }));
      throw new Error(errorMessage);
    }
  }, []);

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
    register,
    logout,
    refreshToken,
    updateUser,
    changePassword,
    clearError,
  };
};
