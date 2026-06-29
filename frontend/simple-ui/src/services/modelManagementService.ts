// Model Management service API client

import { MODEL_VERSION } from '../constants';
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
import type {
  ModelCreateRequest,
  ModelDetails,
  ModelListParams,
  ModelResponse,
  ModelStatusUpdateResponse,
  ModelUpdateRequest,
  PaginatedModels,
  Service,
  UnpublishModelResponse,
} from '../types/platform';
import { PAGINATION } from '../constants/limits';

const REGISTRY_FETCH_PAGE_SIZE = PAGINATION.REGISTRY_FETCH_PAGE_SIZE;
const MAX_REGISTRY_FETCH_PAGES = PAGINATION.MAX_REGISTRY_FETCH_PAGES;

export type {
  ModelCreateRequest,
  ModelDetails,
  ModelListParams,
  ModelResponse,
  ModelStatusUpdateResponse,
  ModelUpdateRequest,
  PaginatedModels,
  UnpublishModelResponse,
} from '../types/platform';

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
      { modelId, versionStatus: MODEL_VERSION.STATUS.DEPRECATED },
      { suppressErrorAlert: true, responseSchema: withPlatformEnvelope(unpublishModelResponseSchema) }
    );
    return response.data;
  } catch (error: unknown) {
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
      suppressErrorAlert: true,
      responseSchema: modelsListSchema,
    });
    return response.data || [];
  } catch (error: unknown) {
    console.error('Get models error:', error);
    throw error;
  }
};

/**
 * Get models with server-side pagination, filtering, and search.
 * Reads the X-Total-Count response header for the accurate total count.
 */

/**
 * Fetches every model matching list filters by walking paginated API pages.
 * Used by the registry UI so name search and table pagination stay consistent (frontend-only).
 */
export const fetchAllModelsMatchingFilters = async (
  params: Pick<ModelListParams, 'taskType' | 'versionStatus' | 'createdBy'> = {}
): Promise<PaginatedModels> => {
  const items: ModelDetails[] = [];
  let total = 0;
  let offset = 0;

  for (let page = 0; page < MAX_REGISTRY_FETCH_PAGES; page++) {
    const result = await getModelsPaginated({
      ...params,
      offset,
      limit: REGISTRY_FETCH_PAGE_SIZE,
    });
    total = result.total;
    items.push(...result.items);
    if (items.length >= total || result.items.length === 0) break;
    offset += REGISTRY_FETCH_PAGE_SIZE;
  }

  return { items, total, offset: 0, limit: null };
};

export const getModelsPaginated = async (params: ModelListParams = {}): Promise<PaginatedModels> => {
  try {
    const queryParams: Record<string, string | number> = {};
    if (params.offset !== undefined && params.offset > 0) queryParams.offset = params.offset;
    if (params.limit !== undefined) queryParams.limit = params.limit;
    if (params.taskType) queryParams.task_type = params.taskType;
    if (params.versionStatus) queryParams.version_status = params.versionStatus;
    if (params.createdBy) queryParams.created_by = params.createdBy;

    const response = await apiService.get(apiEndpoints.platform.models.base, {
      params: queryParams,
      suppressErrorAlert: true,
      responseSchema: modelsListSchema,
    });

    const total = Number.parseInt(response.headers['x-total-count'] ?? '0', 10);
    const payload = response.data;
    const items = Array.isArray(payload) ? payload : [];

    return {
      items,
      total: Number.isNaN(total) ? items.length : total,
      offset: params.offset ?? 0,
      limit: params.limit ?? null,
    };
  } catch (error: unknown) {
    console.error('Get models (paginated) error:', error);
    throw error;
  }
};

/**
 * Create a new model
 * @param modelData - The model data to create
 * @returns Promise with created model
 */
export const createModel = async (modelData: ModelCreateRequest): Promise<ModelResponse> => {
  try {
    const response = await apiService.post(apiEndpoints.platform.models.base, modelData, {
      suppressErrorAlert: true,
      responseSchema: unknownPlatformPayloadSchema,
    });
    return response.data as ModelResponse;
  } catch (error: unknown) {
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
      suppressErrorAlert: true,
      responseSchema: modelSingleSchema,
    });
    return response.data;
  } catch (error: unknown) {
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
export const updateModel = async (modelData: ModelUpdateRequest): Promise<ModelStatusUpdateResponse> => {
  try {
    const response = await apiService.patch(apiEndpoints.platform.models.base, modelData, {
      suppressErrorAlert: true,
      responseSchema: unknownPlatformPayloadSchema,
    });
    return response.data as ModelStatusUpdateResponse;
  } catch (error: unknown) {
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
export const publishModel = async (modelId: string): Promise<ModelStatusUpdateResponse> => {
  try {
    // Platform-core toggles status through the model management PATCH endpoint.
    const response = await apiService.patch(
      apiEndpoints.platform.models.base,
      { modelId, versionStatus: MODEL_VERSION.STATUS.ACTIVE },
      { suppressErrorAlert: true, responseSchema: unknownPlatformPayloadSchema }
    );
    return response.data as ModelStatusUpdateResponse;
  } catch (error: unknown) {
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
): Promise<Service[]> => {
  try {
    const url = apiEndpoints.platform.services.base;
    const params: Record<string, string> = {};
    if (taskType) params.task_type = taskType;
    if (publishedOnly === true) params.is_published = 'true';
    const response = await apiService.get(url, {
      params,
      suppressErrorAlert: true,
      responseSchema: servicesListSchema,
    });
    return response.data || [];
  } catch (error: unknown) {
    console.error('List services error:', error);
    const err = error as { response?: { data?: { detail?: string; message?: string } }; message?: string };
    const errorMessage =
      err?.response?.data?.detail ||
      err?.response?.data?.message ||
      err?.message ||
      'Failed to fetch services';
    throw new Error(errorMessage);
  }
};
