// LLM service API client with typed methods

import { apiService, apiEndpoints } from './api';
import {
  llmHealthResponseSchema,
  llmInferenceResponseSchema,
  llmModelsListSchema,
} from './dto/schemas/inference';
import {
  LLMInferenceRequest,
  LLMInferenceResponse,
  LLMHealthResponse,
  LLMModel
} from '../types/llm';
import { listServices } from './modelManagementService';
import type { Service } from '../types/platform';
import {
  extractLanguageCodes,
  resolveEndpoint,
  resolveModelId,
  resolveModelVersion,
  resolveServiceId,
} from '../utils/platformService';

export interface LLMServiceDetailsResponse {
  service_id: string;
  model_id: string;
  model_version: string;
  name: string;
  serviceDescription: string;
  endpoint: string;
  supported_languages: string[];
}

/**
 * Get list of available LLM services from model management service
 * @returns Promise with LLM services response
 */
export const listLLMServices = async (): Promise<LLMServiceDetailsResponse[]> => {
  try {
    // Fetch services from model management service filtered by task_type='llm'
    const services = await listServices('llm', true);
    const seen = new Set<string>();

    // Transform model management service response to LLMServiceDetailsResponse format
    const normalized = services.map((service: Service) => {
      const supportedLanguages = extractLanguageCodes(service.languages, 'simple');
      const endpoint = resolveEndpoint(service);

      return {
        service_id: resolveServiceId(service),
        model_id: resolveModelId(service),
        model_version: resolveModelVersion(service),
        name: service.name || resolveServiceId(service),
        serviceDescription: service.serviceDescription || service.description || '',
        endpoint,
        supported_languages: supportedLanguages,
      } as LLMServiceDetailsResponse;
    });

    // Deduplicate by service_id in case API returns duplicates
    const uniqueServices: LLMServiceDetailsResponse[] = [];
    for (const svc of normalized) {
      if (!svc.service_id) continue;
      if (seen.has(svc.service_id)) continue;
      seen.add(svc.service_id);
      uniqueServices.push(svc);
    }

    return uniqueServices;
  } catch (error) {
    console.error('Failed to fetch LLM services:', error);
    throw new Error('Failed to fetch LLM services');
  }
};

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

    const response = await apiService.post(apiEndpoints.llm.inference, payload, {
      responseSchema: llmInferenceResponseSchema,
    });

    // Extract response time from headers
    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('LLM inference error:', error);
    throw error; // Re-throw so toast can show backend message via extractErrorInfo
  }
};

/**
 * Get list of available LLM models
 * @returns Promise with LLM models response
 */
export const listLLMModels = async (): Promise<LLMModel[]> => {
  try {
    const response = await apiService.get(apiEndpoints.llm.models, {
      responseSchema: llmModelsListSchema,
    });

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
    const response = await apiService.get(apiEndpoints.llm.health, {
      responseSchema: llmHealthResponseSchema,
    });

    return response.data;
  } catch (error) {
    console.error('Failed to check LLM health:', error);
    throw new Error('Failed to check LLM service health');
  }
};
