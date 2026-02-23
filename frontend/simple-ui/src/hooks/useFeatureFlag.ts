// Custom React hook for feature flag evaluation

import { useQuery } from '@tanstack/react-query';
import { evaluateBooleanFlag, evaluateFeatureFlag, bulkEvaluateFlags } from '../services/featureFlagService';
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

  // Stable queryKey: serialize context so same flag+user+env dedupes (avoid new {} breaking cache)
  const contextKey = typeof context === 'object' && context !== null
    ? JSON.stringify(context)
    : String(context);
  const queryKey = ['feature-flag', flagName, environment, userId, contextKey];

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

const defaultBulkEnv = typeof window !== 'undefined'
  ? (process.env.NEXT_PUBLIC_FEATURE_FLAG_ENVIRONMENT || 'development')
  : 'development';

/** All UI feature flag names (home page + sidebar). Use with useFeatureFlagsBulk for one shared request. */
export const ALL_UI_FEATURE_FLAG_NAMES = [
  'asr-enabled',
  'tts-enabled',
  'nmt-enabled',
  'llm-enabled',
  'pipeline-enabled',
  'model-management-enabled',
  'services-management-enabled',
  'ocr-enabled',
  'transliteration-enabled',
  'language-detection-enabled',
  'speaker-diarization-enabled',
  'language-diarization-enabled',
  'audio-language-detection-enabled',
  'ner-enabled',
] as const;

export interface UseFeatureFlagsBulkOptions {
  flagNames: string[];
  environment?: string;
  defaultValue?: boolean;
  enabled?: boolean;
}

/**
 * Evaluate multiple boolean feature flags in one request (POST /evaluate/bulk).
 * Use this on pages that need many flags (e.g. home page service list) to avoid N separate calls.
 */
export const useFeatureFlagsBulk = (options: UseFeatureFlagsBulkOptions): {
  flags: Record<string, boolean>;
  isLoading: boolean;
  error: Error | null;
  refetch: () => void;
} => {
  const {
    flagNames,
    environment = defaultBulkEnv,
    defaultValue = true,
    enabled = true,
  } = options;

  const { user, isAuthenticated } = useAuth();
  const userId = user?.id ? String(user.id) : user?.username || undefined;

  const queryKey = ['feature-flags-bulk', flagNames.slice().sort().join(','), environment, userId];

  // Only run when authenticated so (1) we send Bearer token and (2) same queryKey for all callers = one request
  const queryEnabled = enabled && flagNames.length > 0 && isAuthenticated;

  const { data, isLoading, error, refetch } = useQuery({
    queryKey,
    queryFn: async () => {
      const defaultFlags = Object.fromEntries(flagNames.map((name) => [name, defaultValue]));
      try {
        const response = await bulkEvaluateFlags({
          flag_names: flagNames,
          user_id: userId,
          environment,
        });
        const results = response?.results;
        if (!results || typeof results !== 'object') {
          return defaultFlags;
        }
        const flags: Record<string, boolean> = {};
        for (const name of flagNames) {
          const r = results[name];
          const v = r?.value;
          const reason = r?.reason;
          // Backend bulk uses default_value=False, so missing/error flags return false; treat as show (defaultValue)
          if (reason === 'ERROR') flags[name] = defaultValue;
          else if (reason === 'DISABLED') flags[name] = false;
          else flags[name] = typeof v === 'boolean' ? v : defaultValue;
        }
        return flags;
      } catch (e) {
        console.debug('Feature flags bulk evaluation failed, using defaults:', e);
        return defaultFlags;
      }
    },
    enabled: queryEnabled,
    staleTime: 30 * 1000,
    gcTime: 5 * 60 * 1000,
    refetchOnWindowFocus: true,
    retry: 1,
    retryOnMount: false,
  });

  // When loading or error, show all as defaultValue so UI (e.g. cards) always renders
  const flags = data ?? Object.fromEntries(flagNames.map((name) => [name, defaultValue]));

  return {
    flags,
    isLoading,
    error: error as Error | null,
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

  // Stable queryKey so same flag+user+env dedupes (context serialized like useFeatureFlag)
  const contextKey = typeof context === 'object' && context !== null
    ? JSON.stringify(context)
    : String(context);
  const queryKey = ['feature-flag-value', flagName, environment, userId, contextKey];

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

