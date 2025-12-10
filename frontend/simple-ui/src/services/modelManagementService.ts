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
    const errorMessage =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      'Failed to unpublish model';
    throw new Error(errorMessage);
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
    const errorMessage =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      'Failed to fetch models';
    throw new Error(errorMessage);
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
    const errorMessage =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      'Failed to create model';
    throw new Error(errorMessage);
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
      `/api/v1/model-management/models/${modelId}`,
      { modelId }
    );
    return response.data;
  } catch (error: any) {
    console.error('Get model error:', error);
    const errorMessage =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      'Failed to fetch model';
    throw new Error(errorMessage);
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
    const errorMessage =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      'Failed to update model';
    throw new Error(errorMessage);
  }
};

/**
 * Publish a model
 * @param modelId - The ID of the model to publish
 * @returns Promise with publish response
 */
export const publishModel = async (modelId: string): Promise<string> => {
  try {
    const response = await apiClient.post<string>(
      `/api/v1/model-management/models/publish?model_id=${encodeURIComponent(modelId)}`
    );
    return response.data;
  } catch (error: any) {
    console.error('Publish model error:', error);
    const errorMessage =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      'Failed to publish model';
    throw new Error(errorMessage);
  }
};

/**
 * List services by task type
 * @param taskType - The task type to filter by (e.g., 'nmt', 'asr', 'tts')
 * @returns Promise with list of services
 */
export const listServices = async (taskType?: string): Promise<any[]> => {
  try {
    const url = '/api/v1/model-management/services/';
    const params = taskType ? { task_type: taskType } : {};
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

