// Pipeline Service API client

import { apiService } from './api';
import { apiEndpoints } from './apiEndpoints';
import { pipelineInferenceResponseSchema, pipelineInfoOrHealthSchema } from './dto/schemas/pipeline';
import {
  PipelineInferenceRequest,
  PipelineInferenceResponse
} from '../types/pipeline';
import { extractInferenceFeedbackMeta } from '../utils/feedbackContext';
import type { InferenceModelMetadata } from '../types/feedback';

const PIPELINE_ENDPOINTS = apiEndpoints.pipeline;

/**
 * Execute a pipeline inference request
 */
export const runPipelineInference = async (
  request: PipelineInferenceRequest
): Promise<{
  data: PipelineInferenceResponse;
  responseTime: number;
  requestId?: string;
  model?: InferenceModelMetadata;
}> => {
  try {
    const response = await apiService.post(
      PIPELINE_ENDPOINTS.inference,
      request,
      { responseSchema: pipelineInferenceResponseSchema, errorService: 'pipeline' }
    );
    const meta = extractInferenceFeedbackMeta(response);
    return {
      data: response.data,
      responseTime: meta.responseTime,
      requestId: meta.requestId,
      model: meta.model,
    };
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
