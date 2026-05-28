// Feature flag service for interacting with config service

import { z } from 'zod';
import { apiService, apiEndpoints } from './api';
import { ApiValidationError } from './dto/apiValidationError';
import {
  featureFlagBooleanEvalSchema,
  featureFlagBulkEvalSchema,
  featureFlagEvaluationResponseSchema,
  featureFlagListResponseSchema,
  featureFlagResponseSchema,
  featureFlagSyncResponseSchema,
} from './dto/schemas/featureFlags';

export interface FeatureFlagEvaluationRequest {
  flag_name: string;
  user_id?: string;
  context?: Record<string, unknown>;
  default_value: boolean | string | number | object;
  environment: string;
}

export type FeatureFlagEvaluationResponse = z.infer<
  typeof featureFlagEvaluationResponseSchema
>;
export type FeatureFlagResponse = z.infer<typeof featureFlagResponseSchema>;
export type FeatureFlagListResponse = z.infer<typeof featureFlagListResponseSchema>;

export interface BulkEvaluationRequest {
  flag_names: string[];
  user_id?: string;
  context?: Record<string, unknown>;
  environment: string;
}

/**
 * Evaluate a single feature flag.
 * Defaults to enabled (true) if evaluation fails or flag doesn't exist.
 * Contract mismatches ({@link ApiValidationError}) always propagate.
 */
export const evaluateFeatureFlag = async (
  request: FeatureFlagEvaluationRequest
): Promise<FeatureFlagEvaluationResponse> => {
  try {
    const defaultValue =
      request.default_value !== undefined
        ? request.default_value
        : typeof request.default_value === 'boolean'
          ? true
          : request.default_value;

    const response = await apiService.post(
      apiEndpoints.featureFlags.evaluate,
      {
        ...request,
        default_value: defaultValue,
      },
      { responseSchema: featureFlagEvaluationResponseSchema }
    );
    return response.data;
  } catch (error: unknown) {
    if (error instanceof ApiValidationError) {
      throw error;
    }
    console.debug(`Feature flag evaluation failed for '${request.flag_name}':`, error);
    const fallbackValue =
      typeof request.default_value === 'boolean' ? true : request.default_value;
    return {
      flag_name: request.flag_name,
      value: fallbackValue as FeatureFlagEvaluationResponse['value'],
      variant: undefined,
      reason: 'ERROR',
      evaluated_at: new Date().toISOString(),
    };
  }
};

/** Evaluate a boolean feature flag (simplified). */
export const evaluateBooleanFlag = async (
  flagName: string,
  environment: string,
  defaultValue: boolean = false,
  userId?: string,
  context?: Record<string, unknown>
): Promise<z.infer<typeof featureFlagBooleanEvalSchema>> => {
  const response = await apiService.post(
    apiEndpoints.featureFlags.evaluateBoolean,
    {
      flag_name: flagName,
      user_id: userId,
      context: context || {},
      default_value: defaultValue,
      environment,
    },
    { responseSchema: featureFlagBooleanEvalSchema }
  );
  return response.data;
};

/** Bulk evaluate multiple feature flags. */
export const bulkEvaluateFlags = async (
  request: BulkEvaluationRequest
): Promise<z.infer<typeof featureFlagBulkEvalSchema>> => {
  const response = await apiService.post(
    apiEndpoints.featureFlags.evaluateBulk,
    request,
    { responseSchema: featureFlagBulkEvalSchema }
  );
  return response.data;
};

/** Get a single feature flag by name. */
export const getFeatureFlag = async (
  name: string,
  environment: string
): Promise<FeatureFlagResponse> => {
  const response = await apiService.get(apiEndpoints.featureFlags.byName(name), {
    params: { environment },
    responseSchema: featureFlagResponseSchema,
  });
  return response.data;
};

/** List all feature flags with pagination. */
export const listFeatureFlags = async (
  environment: string,
  limit: number = 50,
  offset: number = 0
): Promise<FeatureFlagListResponse> => {
  const response = await apiService.get(apiEndpoints.featureFlags.list, {
    params: { environment, limit, offset },
    responseSchema: featureFlagListResponseSchema,
  });
  return response.data;
};

/** Sync/refresh feature flags from Unleash. */
export const syncFeatureFlags = async (
  environment: string
): Promise<z.infer<typeof featureFlagSyncResponseSchema>> => {
  const response = await apiService.post(
    apiEndpoints.featureFlags.sync,
    null,
    {
      params: { environment },
      responseSchema: featureFlagSyncResponseSchema,
    }
  );
  return response.data;
};
