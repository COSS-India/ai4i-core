// Pipeline Service API client

import apiClient, { apiEndpoints } from './api';
import { 
  PipelineInferenceRequest, 
  PipelineInferenceResponse 
} from '../types/pipeline';

/**
 * Execute a pipeline inference request
 */
export const runPipelineInference = async (
  request: PipelineInferenceRequest
): Promise<PipelineInferenceResponse> => {
  try {
    const response = await apiClient.post(
      apiEndpoints.pipeline.inference,
      request
    );
    return response.data;
  } catch (error) {
    console.error('Pipeline inference error:', error);
    throw error; // Re-throw so toast can show backend message via extractErrorInfo
  }
};

/**
 * Get pipeline service information
 */
export const getPipelineInfo = async (): Promise<any> => {
  const response = await apiClient.get(apiEndpoints.pipeline.info);
  return response.data;
};

/**
 * Check pipeline service health
 */
export const checkPipelineHealth = async (): Promise<any> => {
  const response = await apiClient.get(apiEndpoints.pipeline.health);
  return response.data;
};

const pipelineService = {
  runPipelineInference,
  getPipelineInfo,
  checkPipelineHealth,
};

export default pipelineService;
