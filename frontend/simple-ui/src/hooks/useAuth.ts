/**
 * Authentication hook
 */
import { useState, useEffect, useCallback } from 'react';
import { User, AuthState, LoginRequest, RegisterRequest } from '../types/auth';
import authService from '../services/authService';

export const useAuth = () => {
  const [authState, setAuthState] = useState<AuthState>({
    user: null,
    accessToken: null,
    refreshToken: null,
    isAuthenticated: false,
    isLoading: true,
    error: null,
  });

  // Initialize auth state
  useEffect(() => {
    const initializeAuth = async () => {
      try {
        const storedUser = authService.getStoredUser();
        const hasToken = authService.isAuthenticated();

        // Only restore auth state if we have BOTH a valid token AND user data
        if (hasToken && storedUser) {
          // Verify token is still valid by calling /me endpoint
          try {
            const currentUser = await authService.getCurrentUser();
            // Token is valid and we got user data
            setAuthState({
              user: currentUser, // Use fresh user data from API
              accessToken: authService.getAccessToken(),
              refreshToken: authService.getRefreshToken(),
              isAuthenticated: true,
              isLoading: false,
              error: null,
            });
            // Update stored user with fresh data
            authService.setStoredUser(currentUser);
          } catch (error) {
            // Token is invalid or expired, clear everything
            console.log('Token validation failed during initialization, clearing auth state');
            authService.clearAuthTokens();
            authService.clearStoredUser();
            setAuthState({
              user: null,
              accessToken: null,
              refreshToken: null,
              isAuthenticated: false,
              isLoading: false,
              error: null,
            });
          }
        } else {
          // No token or no user data - ensure everything is cleared
          if (!hasToken) {
            authService.clearStoredUser();
          }
          setAuthState({
            user: null,
            accessToken: null,
            refreshToken: null,
            isAuthenticated: false,
            isLoading: false,
            error: null,
          });
        }
      } catch (error) {
        console.error('Auth initialization failed:', error);
        // Clear everything on error
        authService.clearAuthTokens();
        authService.clearStoredUser();
        setAuthState({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
          isLoading: false,
          error: null,
        });
      }
    };

    initializeAuth();
  }, []);

  const login = useCallback(async (credentials: LoginRequest) => {
    setAuthState(prev => ({ ...prev, isLoading: true, error: null }));
    console.log('useAuth: Starting login...');

    try {
      const response = await authService.login(credentials);
      console.log('useAuth: Login API successful, tokens received');
      
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
        
        // Force a small delay to ensure state propagation, then return
        // This helps React batch updates and ensures UI updates immediately
        await new Promise(resolve => setTimeout(resolve, 0));
        
        return response;
      } catch (meError) {
        console.error('useAuth: Failed to fetch user data / token validation failed:', meError);
        // Clear tokens if /me fails (token is invalid or expired)
        authService.clearAuthTokens();
        setAuthState(prev => ({
          ...prev,
          isLoading: false,
          error: 'Token validation failed. Please try logging in again.',
        }));
        throw new Error('Token validation failed. Please try logging in again.');
      }
    } catch (error) {
      console.error('useAuth: Login failed:', error);
      const errorMessage = error instanceof Error ? error.message : 'Login failed';
      setAuthState(prev => ({
        ...prev,
        isLoading: false,
        error: errorMessage,
      }));
      throw error;
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

      // Navigate to home page and refresh to show sign-in button
      if (typeof window !== 'undefined') {
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

      // Navigate to home page even if logout API call failed
      if (typeof window !== 'undefined') {
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
