// Pipeline Service API client

import { apiEndpoints } from './api';
import baseApiService from './baseApiService';
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
    return await baseApiService.post<PipelineInferenceResponse>(
      apiEndpoints.pipeline.inference,
      request
    );
  } catch (error) {
    console.error('Pipeline inference error:', error);
    throw error; // Re-throw so toast can show backend message via extractErrorInfo
  }
};

/**
 * Get pipeline service information
 */
export const getPipelineInfo = async (): Promise<any> => {
  return baseApiService.get(apiEndpoints.pipeline.info);
};

/**
 * Check pipeline service health
 */
export const checkPipelineHealth = async (): Promise<any> => {
  return baseApiService.get(apiEndpoints.pipeline.health);
};

const pipelineService = {
  runPipelineInference,
  getPipelineInfo,
  checkPipelineHealth,
};

export default pipelineService;
