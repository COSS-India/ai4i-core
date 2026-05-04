// Feature flag service for interacting with config service

import { apiClient } from './api';

// Types
export interface FeatureFlagEvaluationRequest {
  flag_name: string;
  user_id?: string;
  context?: Record<string, any>;
  default_value: boolean | string | number | object;
  environment: string;
}

export interface FeatureFlagEvaluationResponse {
  flag_name: string;
  value: boolean | string | number | object;
  variant?: string;
  reason: string;
  evaluated_at: string;
}

export interface FeatureFlagResponse {
  name: string;
  description?: string;
  is_enabled: boolean;
  environment: string;
  rollout_percentage?: string;
  target_users?: string[];
  unleash_flag_name?: string;
  last_synced_at?: string;
  created_at?: string;
  updated_at?: string;
}

export interface FeatureFlagListResponse {
  items: FeatureFlagResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface BulkEvaluationRequest {
  flag_names: string[];
  user_id?: string;
  context?: Record<string, any>;
  environment: string;
}

// API gateway routes /api/v1/feature-flags to config-service
// So we can use the apiClient which already has the base URL configured

/**
 * Evaluate a single feature flag
 * Defaults to enabled (true) if evaluation fails or flag doesn't exist
 */
export const evaluateFeatureFlag = async (
  request: FeatureFlagEvaluationRequest
): Promise<FeatureFlagEvaluationResponse> => {
  try {
    // Ensure default_value is true if not specified (for boolean flags)
    const defaultValue = request.default_value !== undefined 
      ? request.default_value 
      : (typeof request.default_value === 'boolean' ? true : request.default_value);
    
    const response = await apiClient.post<FeatureFlagEvaluationResponse>(
      '/api/v1/feature-flags/evaluate',
      {
        ...request,
        default_value: defaultValue,
      }
    );
    return response.data;
  } catch (error: any) {
    // On any error, return enabled (true) by default
    console.debug(`Feature flag evaluation failed for '${request.flag_name}':`, error);
    return {
      flag_name: request.flag_name,
      value: typeof request.default_value === 'boolean' ? true : request.default_value,
      variant: undefined,
      reason: 'ERROR',
      evaluated_at: new Date().toISOString(),
    };
  }
};

/**
 * Evaluate a boolean feature flag (simplified)
 */
export const evaluateBooleanFlag = async (
  flagName: string,
  environment: string,
  defaultValue: boolean = false,
  userId?: string,
  context?: Record<string, any>
): Promise<{ flag_name: string; value: boolean; reason: string }> => {
  const response = await apiClient.post<{ flag_name: string; value: boolean; reason: string }>(
    '/api/v1/feature-flags/evaluate/boolean',
    {
      flag_name: flagName,
      user_id: userId,
      context: context || {},
      default_value: defaultValue,
      environment,
    }
  );
  return response.data;
};

/**
 * Bulk evaluate multiple feature flags
 */
export const bulkEvaluateFlags = async (
  request: BulkEvaluationRequest
): Promise<{ results: Record<string, FeatureFlagEvaluationResponse> }> => {
  const response = await apiClient.post<{ results: Record<string, FeatureFlagEvaluationResponse> }>(
    '/api/v1/feature-flags/evaluate/bulk',
    request
  );
  return response.data;
};

/**
 * Get a single feature flag by name
 */
export const getFeatureFlag = async (
  name: string,
  environment: string
): Promise<FeatureFlagResponse> => {
  const response = await apiClient.get<FeatureFlagResponse>(
    `/api/v1/feature-flags/${name}`,
    {
      params: { environment },
    }
  );
  return response.data;
};

/**
 * List all feature flags with pagination
 */
export const listFeatureFlags = async (
  environment: string,
  limit: number = 50,
  offset: number = 0
): Promise<FeatureFlagListResponse> => {
  const response = await apiClient.get<FeatureFlagListResponse>(
    '/api/v1/feature-flags',
    {
      params: { environment, limit, offset },
    }
  );
  return response.data;
};

/**
 * Sync/refresh feature flags from Unleash
 */
export const syncFeatureFlags = async (
  environment: string
): Promise<{ synced_count: number; environment: string }> => {
  const response = await apiClient.post<{ synced_count: number; environment: string }>(
    '/api/v1/feature-flags/sync',
    null,
    {
      params: { environment },
    }
  );
  return response.data;
};

