// Language Diarization service API client

import { apiClient, apiEndpoints } from './api';
import { listServices } from './modelManagementService';

export interface LanguageDiarizationServiceDetailsResponse {
  service_id: string;
  model_id: string;
  model_version: string;
  name: string;
  serviceDescription: string;
  endpoint: string;
  supported_languages: string[];
}

export interface LanguageDiarizationInferenceRequest {
  audio: Array<{
    audioContent: string;
  }>;
  config: {
    serviceId: string;
    [key: string]: any;
  };
}

export interface LanguageDiarizationInferenceResponse {
  output: Array<{
    segments?: Array<{
      start: number;
      end: number;
      language: string;
    }>;
    [key: string]: any;
  }>;
}

/**
 * Get list of available Language Diarization services from model management service
 * @returns Promise with Language Diarization services response
 */
export const listLanguageDiarizationServices = async (): Promise<LanguageDiarizationServiceDetailsResponse[]> => {
  try {
    // Fetch services from model management service filtered by task_type='language-diarization'
    const services = await listServices('language-diarization');
    const seen = new Set<string>();

    // Transform model management service response to LanguageDiarizationServiceDetailsResponse format
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
      } as LanguageDiarizationServiceDetailsResponse;
    });

    // Deduplicate by service_id in case API returns duplicates
    const uniqueServices: LanguageDiarizationServiceDetailsResponse[] = [];
    for (const svc of normalized) {
      if (!svc.service_id) continue;
      if (seen.has(svc.service_id)) continue;
      seen.add(svc.service_id);
      uniqueServices.push(svc);
    }

    return uniqueServices;
  } catch (error) {
    console.error('Failed to fetch Language Diarization services:', error);
    throw new Error('Failed to fetch Language Diarization services');
  }
};

/**
 * Perform language diarization inference
 */
export const performLanguageDiarizationInference = async (
  audioContent: string,
  serviceId: string
): Promise<{ data: LanguageDiarizationInferenceResponse; responseTime: number }> => {
  try {
    const payload: LanguageDiarizationInferenceRequest = {
      audio: [{ audioContent }],
      config: {
        serviceId,
      },
    };

    const response = await apiClient.post<LanguageDiarizationInferenceResponse>(
      apiEndpoints['language-diarization'].inference,
      payload
    );

    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('Language diarization inference error:', error);
    throw error;
  }
};

