// Pipeline Service API client

import apiClient from './api';
import { 
  PipelineInferenceRequest, 
  PipelineInferenceResponse 
} from '../types/pipeline';

const PIPELINE_ENDPOINTS = {
  inference: '/api/v1/pipeline/inference',
  info: '/api/v1/pipeline/info',
  health: '/api/v1/pipeline/health',
} as const;

/**
 * Execute a pipeline inference request
 */
export const runPipelineInference = async (
  request: PipelineInferenceRequest
): Promise<PipelineInferenceResponse> => {
  try {
    const response = await apiClient.post(
      PIPELINE_ENDPOINTS.inference,
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
  const response = await apiClient.get(PIPELINE_ENDPOINTS.info);
  return response.data;
};

/**
 * Check pipeline service health
 */
export const checkPipelineHealth = async (): Promise<any> => {
  const response = await apiClient.get(PIPELINE_ENDPOINTS.health);
  return response.data;
};

const pipelineService = {
  runPipelineInference,
  getPipelineInfo,
  checkPipelineHealth,
};

export default pipelineService;
