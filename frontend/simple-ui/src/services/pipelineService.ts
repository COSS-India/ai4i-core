// Pipeline Service API client

import { apiService } from './api';
import { apiEndpoints } from './apiEndpoints';
import { pipelineInferenceResponseSchema, pipelineInfoOrHealthSchema } from './dto/schemas/pipeline';
import {
  PipelineInferenceRequest,
  PipelineInferenceResponse
} from '../types/pipeline';

const PIPELINE_ENDPOINTS = apiEndpoints.pipeline;

/**
 * Execute a pipeline inference request
 */
export const runPipelineInference = async (
  request: PipelineInferenceRequest
): Promise<PipelineInferenceResponse> => {
  try {
    const response = await apiService.post(
      PIPELINE_ENDPOINTS.inference,
      request,
      { responseSchema: pipelineInferenceResponseSchema, errorService: 'pipeline' }
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
  const response = await apiService.get(PIPELINE_ENDPOINTS.info, {
    responseSchema: pipelineInfoOrHealthSchema,
  });
  return response.data;
};

/**
 * Check pipeline service health
 */
export const checkPipelineHealth = async (): Promise<any> => {
  const response = await apiService.get(PIPELINE_ENDPOINTS.health, {
    responseSchema: pipelineInfoOrHealthSchema,
  });
  return response.data;
};

const pipelineService = {
  runPipelineInference,
  getPipelineInfo,
  checkPipelineHealth,
};

export default pipelineService;
