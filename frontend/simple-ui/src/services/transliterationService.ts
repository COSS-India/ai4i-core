// Transliteration service API client

import { apiClient, apiEndpoints } from './api';
import { listServices } from './modelManagementService';

export interface TransliterationServiceDetailsResponse {
  service_id: string;
  model_id: string;
  model_version: string;
  name: string;
  serviceDescription: string;
  endpoint: string;
  supported_languages: string[];
}

export interface TransliterationInferenceRequest {
  input: Array<{
    source: string;
  }>;
  config: {
    serviceId: string;
    language: {
      sourceLanguage: string;
      targetLanguage: string;
      sourceScriptCode?: string;
      targetScriptCode?: string;
    };
    isSentence?: boolean;
    numSuggestions?: number;
  };
  controlConfig?: {
    [key: string]: any;
  };
}

export interface TransliterationInferenceResponse {
  output: Array<{
    source: string;
    target: string;
    [key: string]: any;
  }>;
}

/**
 * Get list of available Transliteration services from model management service
 * @returns Promise with Transliteration services response
 */
export const listTransliterationServices = async (): Promise<TransliterationServiceDetailsResponse[]> => {
  try {
    // Fetch services from model management service filtered by task_type='transliteration'
    const services = await listServices('transliteration', true);
    const seen = new Set<string>();

    // Transform model management service response to TransliterationServiceDetailsResponse format
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
      } as TransliterationServiceDetailsResponse;
    });

    // Deduplicate by service_id in case API returns duplicates
    const uniqueServices: TransliterationServiceDetailsResponse[] = [];
    for (const svc of normalized) {
      if (!svc.service_id) continue;
      if (seen.has(svc.service_id)) continue;
      seen.add(svc.service_id);
      uniqueServices.push(svc);
    }

    return uniqueServices;
  } catch (error) {
    console.error('Failed to fetch Transliteration services:', error);
    throw new Error('Failed to fetch Transliteration services');
  }
};

/**
 * Perform transliteration inference
 */
export const performTransliterationInference = async (
  text: string,
  config: TransliterationInferenceRequest['config']
): Promise<{ data: TransliterationInferenceResponse; responseTime: number }> => {
  try {
    const payload: TransliterationInferenceRequest = {
      input: [{ source: text }],
      config: {
        ...config,
        isSentence: config.isSentence ?? true,
        numSuggestions: config.numSuggestions ?? 0,
      },
    };

    const response = await apiClient.post<TransliterationInferenceResponse>(
      apiEndpoints.transliteration.inference,
      payload
    );

    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('Transliteration inference error:', error);
    throw error; // Re-throw so toast can show backend message via extractErrorInfo
  }
};

