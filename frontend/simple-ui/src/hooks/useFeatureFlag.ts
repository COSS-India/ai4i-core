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
  const {
    flagName,
    environment = 'development', // Default environment
    defaultValue = false,
    enabled = true,
    context = {},
  } = options;

  const { user } = useAuth();
  // Convert user ID to string if it exists, otherwise use username or undefined
  const userId = user?.id ? String(user.id) : user?.username || undefined;

  const {
    data,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['feature-flag', flagName, environment, userId, context],
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
    cacheTime: 5 * 60 * 1000, // Keep in cache for 5 minutes
    refetchOnWindowFocus: true, // Refetch when window regains focus
    retry: 1,
  });

  // If reason is DISABLED, the flag is disabled regardless of value
  // The backend returns default_value when disabled, but we want false for boolean flags
  const isEnabled = data?.reason === 'DISABLED' 
    ? false 
    : (data?.value ?? defaultValue);

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
  const {
    flagName,
    environment = 'development',
    defaultValue,
    enabled = true,
    context = {},
  } = options;

  const { user } = useAuth();
  // Convert user ID to string if it exists, otherwise use username or undefined
  const userId = user?.id ? String(user.id) : user?.username || undefined;

  const {
    data,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ['feature-flag-value', flagName, environment, userId, context],
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
    cacheTime: 5 * 60 * 1000, // Keep in cache for 5 minutes
    refetchOnWindowFocus: true, // Refetch when window regains focus
    retry: 1,
  });

  return {
    value: (data?.value ?? defaultValue) as T,
    isLoading,
    error: error as Error | null,
    reason: data?.reason,
    variant: data?.variant,
    refetch,
  };
};

