// Language Detection service API client

import { apiService, apiEndpoints } from './api';
import { languageDetectionInferenceResponseSchema } from './dto/schemas/inference';
import type {
  LanguageDetectionInferenceRequest,
  LanguageDetectionInferenceResponse,
  LanguagePrediction,
} from '../types/inference';
import { listServices } from './modelManagementService';

export interface LanguageDetectionServiceDetailsResponse {
  service_id: string;
  model_id: string;
  model_version: string;
  name: string;
  serviceDescription: string;
  endpoint: string;
  supported_languages: string[];
}

export type {
  LanguageDetectionInferenceRequest,
  LanguageDetectionInferenceResponse,
  LanguagePrediction,
} from '../types/inference';

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
      { responseSchema: languageDetectionInferenceResponseSchema, errorService: 'language-detection' }
    );

    const responseTime = Number.parseInt(response.headers['request-duration'] || '0', 10);

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('Language detection inference error:', error);
    throw error; // Re-throw so toast can show backend message via extractErrorInfo
  }
};
