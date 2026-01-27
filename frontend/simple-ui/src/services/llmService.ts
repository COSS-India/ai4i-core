// LLM service API client with typed methods

import { llmApiClient, apiEndpoints } from './api';
import { 
  LLMInferenceRequest, 
  LLMInferenceResponse, 
  LLMHealthResponse,
  LLMModel
} from '../types/llm';
import { listServices } from './modelManagementService';

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
    const services = await listServices('llm');
    const seen = new Set<string>();

    // Transform model management service response to LLMServiceDetailsResponse format
    const normalized = services.map((service: any) => {
      // Extract languages from service.languages array
      const supportedLanguages: string[] = [];
      if (service.languages && Array.isArray(service.languages)) {
        service.languages.forEach((lang: any) => {
          if (typeof lang === 'string') {
            supportedLanguages.push(lang);
          } else if (lang && typeof lang === 'object') {
            // Handle different language object formats
            const langCode = lang.code || lang.language;
            if (langCode) {
              supportedLanguages.push(langCode);
            }
          }
        });
      }
      
      // Extract endpoint and clean it
      let endpoint = service.endpoint || '';
      if (endpoint) {
        endpoint = endpoint.replace('http://', '').replace('https://', '');
      }
      
      return {
        service_id: service.serviceId || service.service_id,
        model_id: service.modelId || service.model_id,
        model_version: service.modelVersion || service.model_version || '',
        name: service.name || service.serviceId || '',
        serviceDescription: service.serviceDescription || service.description || '',
        endpoint: endpoint,
        supported_languages: Array.from(new Set(supportedLanguages)), // Remove duplicates
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

    const response = await llmApiClient.post<LLMInferenceResponse>(
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
    const response = await llmApiClient.get<{ models: LLMModel[]; total_models: number }>(
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
    const response = await llmApiClient.get<LLMHealthResponse>(
      apiEndpoints.llm.health
    );

    return response.data;
  } catch (error) {
    console.error('Failed to check LLM health:', error);
    throw new Error('Failed to check LLM service health');
  }
};

