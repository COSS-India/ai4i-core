// Model Management service API client

import { apiClient } from './api';

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
    // The API expects model_id as a query parameter
    const response = await apiClient.post<UnpublishModelResponse>(
      `/api/v1/model-management/models/unpublish?model_id=${encodeURIComponent(modelId)}`
    );
    return response.data;
  } catch (error: any) {
    console.error('Unpublish model error:', error);
    // Don't transform the error - let extractErrorInfo handle it
    throw error;
  }
};

/**
 * Get all models
 * @returns Promise with list of models
 */
export const getAllModels = async (): Promise<any[]> => {
  try {
    const response = await apiClient.get<any[]>('/api/v1/model-management/models');
    return response.data;
  } catch (error: any) {
    console.error('Get models error:', error);
    // Don't transform the error - let extractErrorInfo handle it
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
    const response = await apiClient.post<any>('/api/v1/model-management/models', modelData);
    return response.data;
  } catch (error: any) {
    console.error('Create model error:', error);
    // Don't transform the error - let extractErrorInfo handle it
    throw error;
  }
};

/**
 * Get a model by ID
 * @param modelId - The ID of the model to fetch
 * @returns Promise with model details
 */
export const getModelById = async (modelId: string): Promise<any> => {
  try {
    const response = await apiClient.post<any>(
      `/api/v1/model-management/models/${encodeURIComponent(modelId)}`,
      { modelId }
    );
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
    const response = await apiClient.patch<any>('/api/v1/model-management/models', modelData);
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
    const response = await apiClient.post<any>(
      `/api/v1/model-management/models/publish?model_id=${encodeURIComponent(modelId)}`
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
    const url = '/api/v1/model-management/services';
    const params: Record<string, string> = {};
    if (taskType) params.task_type = taskType;
    if (publishedOnly === true) params.is_published = 'true';
    const response = await apiClient.get<any[]>(url, { params });
    return response.data;
  } catch (error: any) {
    console.error('List services error:', error);
    const errorMessage =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      'Failed to fetch services';
    throw new Error(errorMessage);
  }
};

