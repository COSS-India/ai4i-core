// Language Detection service API client

import { apiService, apiEndpoints } from './api';
import { languageDetectionInferenceResponseSchema } from './dto/schemas/inference';
import { listServices } from './modelManagementService';
import type { Service } from '../types/platform';
import {
  extractLanguageCodes,
  resolveEndpoint,
  resolveModelId,
  resolveModelVersion,
  resolveServiceId,
  stripEndpointProtocol,
} from '../utils/platformService';

export interface LanguageDetectionServiceDetailsResponse {
  service_id: string;
  model_id: string;
  model_version: string;
  name: string;
  serviceDescription: string;
  endpoint: string;
  supported_languages: string[];
}

export interface LanguageDetectionInferenceRequest {
  input: Array<{
    source: string;
  }>;
  config: {
    serviceId: string;
  };
}

export interface LanguagePrediction {
  langCode: string;
  scriptCode: string;
  langScore: number;
  language: string;
}

export interface LanguageDetectionInferenceResponse {
  output: Array<{
    source: string;
    langPrediction: LanguagePrediction[];
    [key: string]: any;
  }>;
}

/**
 * Get list of available Language Detection services from model management service
 * @returns Promise with Language Detection services response
 */
export const listLanguageDetectionServices = async (): Promise<LanguageDetectionServiceDetailsResponse[]> => {
  try {
    // Fetch services from model management service filtered by task_type='language-detection'
    const services = await listServices('language-detection', true);
    const seen = new Set<string>();

    // Transform model management service response to LanguageDetectionServiceDetailsResponse format
    const normalized = services.map((service: Service) => {
      const supportedLanguages = extractLanguageCodes(service.languages, 'simple');
      const endpoint = stripEndpointProtocol(resolveEndpoint(service));

      return {
        service_id: resolveServiceId(service),
        model_id: resolveModelId(service),
        model_version: resolveModelVersion(service),
        name: service.name || resolveServiceId(service),
        serviceDescription: service.serviceDescription || service.description || '',
        endpoint,
        supported_languages: supportedLanguages,
      } as LanguageDetectionServiceDetailsResponse;
    });

    // Deduplicate by service_id in case API returns duplicates
    const uniqueServices: LanguageDetectionServiceDetailsResponse[] = [];
    for (const svc of normalized) {
      if (!svc.service_id) continue;
      if (seen.has(svc.service_id)) continue;
      seen.add(svc.service_id);
      uniqueServices.push(svc);
    }

    return uniqueServices;
  } catch (error) {
    console.error('Failed to fetch Language Detection services:', error);
    throw new Error('Failed to fetch Language Detection services');
  }
};

/**
 * Perform language detection inference
 */
export const performLanguageDetectionInference = async (
  texts: string[],
  serviceId: string
): Promise<{ data: LanguageDetectionInferenceResponse; responseTime: number }> => {
  try {
    const payload: LanguageDetectionInferenceRequest = {
      input: texts.map(text => ({ source: text })),
      config: {
        serviceId,
      },
    };

    const response = await apiService.post(
      apiEndpoints['language-detection'].inference,
      payload,
      { responseSchema: languageDetectionInferenceResponseSchema }
    );

    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('Language detection inference error:', error);
    throw error; // Re-throw so toast can show backend message via extractErrorInfo
  }
};
