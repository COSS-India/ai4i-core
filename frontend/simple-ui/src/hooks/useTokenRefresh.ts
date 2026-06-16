/**
 * Custom hook for proactive token refresh
 * Automatically refreshes tokens before they expire
 */
import { useEffect, useRef, useCallback } from 'react';
import authService from '../services/authService';

interface UseTokenRefreshOptions {
  /**
   * Enable automatic background refresh
   * Default: true
   */
  enableBackgroundRefresh?: boolean;
  
  /**
   * Refresh interval in milliseconds
   * Default: 5 minutes (300000ms)
   */
  refreshInterval?: number;
  
  /**
   * Threshold in minutes before expiry to trigger refresh
   * Default: 5 minutes
   */
  refreshThresholdMinutes?: number;
}

/**
 * Hook to manage automatic token refresh
 * 
 * Usage:
 * ```typescript
 * const { refreshToken, isRefreshing } = useTokenRefresh({
 *   enableBackgroundRefresh: true,
 *   refreshInterval: 300000, // 5 minutes
 *   refreshThresholdMinutes: 5
 * });
 * ```
 */
export const useTokenRefresh = (options: UseTokenRefreshOptions = {}) => {
  const {
    enableBackgroundRefresh = true,
    refreshInterval = 300000, // 5 minutes
    refreshThresholdMinutes = 5,
  } = options;

  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const isRefreshingRef = useRef(false);

  /**
   * Manually refresh token if expiring soon
   */
  const refreshToken = useCallback(async () => {
    if (isRefreshingRef.current) {
      return false; // Already refreshing, skip
    }

    isRefreshingRef.current = true;
    try {
      const result = await authService.refreshIfExpiringSoon(refreshThresholdMinutes);
      return result;
    } catch (error) {
      console.error('Token refresh failed:', error);
      return false;
    } finally {
      isRefreshingRef.current = false;
    }
  }, [refreshThresholdMinutes]);

  /**
   * Check token status
   */
  const getTokenStatus = useCallback(() => {
    const isExpired = authService.isTokenExpired();
    const isExpiringSoon = authService.isTokenExpiringSoon(refreshThresholdMinutes);
    const timeUntilExpiry = authService.getTimeUntilExpiry();

    return {
      isExpired,
      isExpiringSoon,
      timeUntilExpiry,
      timeUntilExpiryMinutes: timeUntilExpiry ? Math.floor(timeUntilExpiry / 60000) : null,
    };
  }, [refreshThresholdMinutes]);

  // Setup background refresh if enabled
  useEffect(() => {
    if (!enableBackgroundRefresh) {
      return;
    }

    // Initial check
    refreshToken();

    // Setup interval for periodic checks
    intervalRef.current = setInterval(() => {
      refreshToken();
    }, refreshInterval);

    // Cleanup
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [enableBackgroundRefresh, refreshInterval, refreshToken]);

  // Listen for page visibility changes to refresh when user comes back
  useEffect(() => {
    if (!enableBackgroundRefresh) {
      return;
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        // Page became visible, check if we need to refresh
        refreshToken();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [enableBackgroundRefresh, refreshToken]);

  return {
    refreshToken,
    getTokenStatus,
    isRefreshing: isRefreshingRef.current,
  };
};

export default useTokenRefresh;



