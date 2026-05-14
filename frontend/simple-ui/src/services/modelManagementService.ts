// Model Management service API client

import { apiService } from './api';
import { apiEndpoints } from './apiEndpoints';
import {
  modelsListSchema,
  modelSingleSchema,
  servicesListSchema,
  unknownPlatformPayloadSchema,
  unpublishModelResponseSchema,
  withPlatformEnvelope,
} from './dto/schemas/platform';

export interface ModelDetails {
  modelId?: string;
  model_id?: string;
  name?: string;
  versionStatus?: string;
  version_status?: string;
  task?: { type?: string };
  task_type?: string;
  taskType?: string;
  version?: string;
  modelVersion?: string;
  submittedOn?: string | number;
  submitted_on?: string | number;
  [key: string]: any;
}

export interface ModelListParams {
  offset?: number;
  limit?: number;
  taskType?: string;
  versionStatus?: string;
  createdBy?: string;
}

export interface PaginatedModels {
  items: ModelDetails[];
  total: number;
  offset: number;
  limit: number | null;
}

export interface UnpublishModelResponse {
  message: string;
  modelId: string;
  success: boolean;
}

/**
 * Unpublish a model
 * @param modelId - The ID of the model to unpublish
 * @returns Promise with unpublish response
 */
export const unpublishModel = async (
  modelId: string
): Promise<UnpublishModelResponse> => {
  try {
    // Platform-core toggles status through the model management PATCH endpoint.
    const response = await apiService.patch(
      apiEndpoints.platform.models.base,
      { modelId, versionStatus: 'DEPRECATED' },
      { responseSchema: withPlatformEnvelope(unpublishModelResponseSchema) }
    );
    return response.data;
  } catch (error: any) {
    console.error('Unpublish model error:', error);
    // Don't transform the error - let extractErrorInfo handle it
    throw error;
  }
};

/**
 * Get all models (no pagination — returns everything, backward-compatible)
 * @returns Promise with list of models
 */
export const getAllModels = async (): Promise<ModelDetails[]> => {
  try {
    const response = await apiService.get(apiEndpoints.platform.models.base, {
      responseSchema: modelsListSchema,
    });
    return response.data || [];
  } catch (error: any) {
    console.error('Get models error:', error);
    throw error;
  }
};

/**
 * Get models with server-side pagination, filtering, and search.
 * Reads the X-Total-Count response header for the accurate total count.
 */
export const getModelsPaginated = async (params: ModelListParams = {}): Promise<PaginatedModels> => {
  try {
    const queryParams: Record<string, any> = {};
    if (params.offset !== undefined && params.offset > 0) queryParams.offset = params.offset;
    if (params.limit !== undefined) queryParams.limit = params.limit;
    if (params.taskType) queryParams.task_type = params.taskType;
    if (params.versionStatus) queryParams.version_status = params.versionStatus;
    if (params.createdBy) queryParams.created_by = params.createdBy;

    const response = await apiService.get(apiEndpoints.platform.models.base, {
      params: queryParams,
      responseSchema: modelsListSchema,
    });

    const total = parseInt(response.headers['x-total-count'] ?? '0', 10);
    const payload = response.data;
    const items = Array.isArray(payload) ? payload : [];

    return {
      items,
      total: Number.isNaN(total) ? items.length : total,
      offset: params.offset ?? 0,
      limit: params.limit ?? null,
    };
  } catch (error: any) {
    console.error('Get models (paginated) error:', error);
    throw error;
  }
};

/**
 * Create a new model
 * @param modelData - The model data to create
 * @returns Promise with created model
 */
export const createModel = async (modelData: any): Promise<any> => {
  try {
    const response = await apiService.post(apiEndpoints.platform.models.base, modelData, {
      responseSchema: unknownPlatformPayloadSchema,
    });
    return response.data;
  } catch (error: any) {
    console.error('Register model error:', error);
    // Don't transform the error - let extractErrorInfo handle it
    throw error;
  }
};

/**
 * Get a model by ID
 * @param modelId - The ID of the model to fetch
 * @returns Promise with model details
 */
export const getModelById = async (modelId: string): Promise<ModelDetails> => {
  try {
    const response = await apiService.get(apiEndpoints.platform.models.byId(modelId), {
      responseSchema: modelSingleSchema,
    });
    return response.data;
  } catch (error: any) {
    console.error('Get model error:', error);
    // Don't transform the error - let extractErrorInfo handle it
    throw error;
  }
};

/**
 * Update a model
 * @param modelData - The model data to update
 * @returns Promise with update response
 */
export const updateModel = async (modelData: any): Promise<any> => {
  try {
    const response = await apiService.patch(apiEndpoints.platform.models.base, modelData, {
      responseSchema: unknownPlatformPayloadSchema,
    });
    return response.data;
  } catch (error: any) {
    console.error('Update model error:', error);
    // Don't transform the error - let extractErrorInfo handle it
    throw error;
  }
};

/**
 * Publish a model
 * @param modelId - The ID of the model to publish
 * @returns Promise with publish response
 */
export const publishModel = async (modelId: string): Promise<any> => {
  try {
    // Platform-core toggles status through the model management PATCH endpoint.
    const response = await apiService.patch(
      apiEndpoints.platform.models.base,
      { modelId, versionStatus: 'ACTIVE' },
      { responseSchema: unknownPlatformPayloadSchema }
    );
    return response.data;
  } catch (error: any) {
    console.error('Publish model error:', error);
    // Don't transform the error - let extractErrorInfo handle it
    throw error;
  }
};

/**
 * List services by task type
 * @param taskType - The task type to filter by (e.g., 'nmt', 'asr', 'tts')
 * @param publishedOnly - If true, return only published services (for logged-in users)
 * @returns Promise with list of services
 */
export const listServices = async (
  taskType?: string,
  publishedOnly?: boolean
): Promise<any[]> => {
  try {
    const url = apiEndpoints.platform.services.base;
    const params: Record<string, string> = {};
    if (taskType) params.task_type = taskType;
    if (publishedOnly === true) params.is_published = 'true';
    const response = await apiService.get(url, {
      params,
      responseSchema: servicesListSchema,
    });
    return response.data || [];
  } catch (error: any) {
    console.error('List services error:', error);
    const errorMessage =
      error?.response?.data?.detail ||
      error?.response?.data?.message ||
      error?.message ||
      'Failed to fetch services';
    throw new Error(errorMessage);
  }
};
