// Custom React hook for feature flag evaluation

import { useQuery } from '@tanstack/react-query';
import { evaluateBooleanFlag, evaluateFeatureFlag } from '../services/featureFlagService';
import { useAuth } from './useAuth';

export interface UseFeatureFlagOptions {
  flagName: string;
  environment?: string;
  defaultValue?: boolean;
  enabled?: boolean; // Whether the query should run
  context?: Record<string, any>; // Additional context for targeting
}

export interface UseFeatureFlagReturn {
  isEnabled: boolean;
  isLoading: boolean;
  error: Error | null;
  reason?: string;
  refetch: () => void;
}

/**
 * Hook to evaluate a boolean feature flag
 * 
 * @example
 * ```tsx
 * const { isEnabled, isLoading } = useFeatureFlag({
 *   flagName: 'new-ui-enabled',
 *   environment: 'development'
 * });
 * 
 * if (isEnabled) {
 *   return <NewUIComponent />;
 * }
 * return <OldUIComponent />;
 * ```
 */
export const useFeatureFlag = (options: UseFeatureFlagOptions): UseFeatureFlagReturn => {
  // Get environment from env var or use default
  const defaultEnv = typeof window !== 'undefined' 
    ? (process.env.NEXT_PUBLIC_FEATURE_FLAG_ENVIRONMENT || 'development')
    : 'development';
  
  const {
    flagName,
    environment = defaultEnv, // Use env var or default to 'development'
    defaultValue = true, // Changed default to true (enabled by default)
    enabled = true,
    context = {},
  } = options;

  const { user } = useAuth();
  // Convert user ID to string if it exists, otherwise use username or undefined
  const userId = user?.id ? String(user.id) : user?.username || undefined;

  const queryKey = ['feature-flag', flagName, environment, userId, context];
  
  const {
    data,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey,
    queryFn: async () => {
      return await evaluateBooleanFlag(
        flagName,
        environment,
        defaultValue,
        userId,
        context
      );
    },
    enabled: enabled && !!flagName,
    staleTime: 30 * 1000, // Consider data fresh for 30 seconds
    gcTime: 5 * 60 * 1000, // Keep in cache for 5 minutes (renamed from cacheTime in v5)
    refetchOnWindowFocus: true, // Refetch when window regains focus
    retry: 1,
    // On error, return enabled (true) by default
    retryOnMount: false,
  });

  // Default to enabled (true) if there's an error or no data
  // Only disable if explicitly disabled by backend (reason === 'DISABLED')
  const isEnabled = error 
    ? true // Enabled by default on error
    : (data?.reason === 'DISABLED' 
      ? false 
      : (data?.value ?? defaultValue));

  return {
    isEnabled,
    isLoading,
    error: error as Error | null,
    reason: data?.reason,
    refetch,
  };
};

/**
 * Hook to evaluate a feature flag with full details (supports all types)
 * 
 * @example
 * ```tsx
 * const { value, isLoading } = useFeatureFlagValue({
 *   flagName: 'max-upload-size',
 *   environment: 'production',
 *   defaultValue: 10
 * });
 * ```
 */
export const useFeatureFlagValue = <T extends boolean | string | number | object = any>(
  options: Omit<UseFeatureFlagOptions, 'defaultValue'> & { defaultValue: T }
): {
  value: T;
  isLoading: boolean;
  error: Error | null;
  reason?: string;
  variant?: string;
  refetch: () => void;
} => {
  // Get environment from env var or use default
  const defaultEnv = typeof window !== 'undefined' 
    ? (process.env.NEXT_PUBLIC_FEATURE_FLAG_ENVIRONMENT || 'development')
    : 'development';
  
  const {
    flagName,
    environment = defaultEnv, // Use env var or default to 'development'
    defaultValue,
    enabled = true,
    context = {},
  } = options;

  const { user } = useAuth();
  // Convert user ID to string if it exists, otherwise use username or undefined
  const userId = user?.id ? String(user.id) : user?.username || undefined;

  const queryKey = ['feature-flag-value', flagName, environment, userId, context];
  
  const {
    data,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey,
    queryFn: async () => {
      return await evaluateFeatureFlag({
        flag_name: flagName,
        user_id: userId,
        context,
        default_value: defaultValue,
        environment,
      });
    },
    enabled: enabled && !!flagName,
    staleTime: 30 * 1000, // Consider data fresh for 30 seconds
    gcTime: 5 * 60 * 1000, // Keep in cache for 5 minutes (renamed from cacheTime in v5)
    refetchOnWindowFocus: true, // Refetch when window regains focus
    retry: 1,
    retryOnMount: false,
  });

  // For boolean flags, default to enabled (true) on error
  // For other types, use the provided default value
  const fallbackValue = error && typeof defaultValue === 'boolean' 
    ? true as T  // Enabled by default for boolean flags on error
    : defaultValue;

  return {
    value: (data?.value ?? fallbackValue) as T,
    isLoading,
    error: error as Error | null,
    reason: data?.reason,
    variant: data?.variant,
    refetch,
  };
};

