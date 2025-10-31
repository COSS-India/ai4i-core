// LLM service API client with typed methods

import { apiClient, apiEndpoints } from './api';
import { 
  LLMInferenceRequest, 
  LLMInferenceResponse, 
  LLMHealthResponse,
  LLMModel
} from '../types/llm';

/**
 * Perform LLM inference on text
 * @param text - Text to process
 * @param config - LLM configuration
 * @returns Promise with LLM inference response and timing info
 */
export const performLLMInference = async (
  text: string,
  config: LLMInferenceRequest['config']
): Promise<{ data: LLMInferenceResponse; responseTime: number }> => {
  try {
    const payload: LLMInferenceRequest = {
      input: [{ source: text }],
      config,
      controlConfig: {
        dataTracking: false,
      },
    };

    const response = await apiClient.post<LLMInferenceResponse>(
      apiEndpoints.llm.inference,
      payload
    );

    // Extract response time from headers
    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('LLM inference error:', error);
    throw new Error('Failed to perform LLM inference');
  }
};

/**
 * Get list of available LLM models
 * @returns Promise with LLM models response
 */
export const listLLMModels = async (): Promise<LLMModel[]> => {
  try {
    const response = await apiClient.get<{ models: LLMModel[]; total_models: number }>(
      apiEndpoints.llm.models
    );

    return response.data.models;
  } catch (error) {
    console.error('Failed to fetch LLM models:', error);
    throw new Error('Failed to fetch LLM models');
  }
};

/**
 * Check LLM service health
 * @returns Promise with health status
 */
export const checkLLMHealth = async (): Promise<LLMHealthResponse> => {
  try {
    const response = await apiClient.get<LLMHealthResponse>(
      apiEndpoints.llm.health
    );

    return response.data;
  } catch (error) {
    console.error('Failed to check LLM health:', error);
    throw new Error('Failed to check LLM service health');
  }
};

