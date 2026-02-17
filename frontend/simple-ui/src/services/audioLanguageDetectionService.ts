// Audio Language Detection service API client

import { apiClient, apiEndpoints } from './api';
import { listServices } from './modelManagementService';

export interface AudioLanguageDetectionServiceDetailsResponse {
  service_id: string;
  model_id: string;
  model_version: string;
  name: string;
  serviceDescription: string;
  endpoint: string;
  supported_languages: string[];
}

export interface AudioLanguageDetectionInferenceRequest {
  audio: Array<{
    audioContent: string;
  }>;
  config: {
    serviceId: string;
    [key: string]: any;
  };
}

export interface AudioLanguageDetectionInferenceResponse {
  output: Array<{
    detectedLanguage?: string;
    confidence?: number;
    [key: string]: any;
  }>;
}

/**
 * List all available audio language detection services
 */
export const listAudioLanguageDetectionServices = async (): Promise<AudioLanguageDetectionServiceDetailsResponse[]> => {
  try {
    const services = await listServices('audio-lang-detection');
    
    // Transform to AudioLanguageDetectionServiceDetailsResponse format
    const transformedServices = services.map((service: any) => {
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
        model_id: service.modelId || service.model_id || '',
        model_version: service.modelVersion || service.model_version || '',
        name: service.name || service.serviceId || '',
        serviceDescription: service.serviceDescription || service.description || 'No description available',
        endpoint: endpoint,
        supported_languages: supportedLanguages,
      };
    });

    // Remove duplicates based on service_id
    const uniqueServices = transformedServices.filter(
      (service, index, self) =>
        index === self.findIndex((s) => s.service_id === service.service_id)
    );

    return uniqueServices;
  } catch (error) {
    console.error('Failed to fetch audio language detection services:', error);
    throw new Error('Failed to fetch audio language detection services');
  }
};

/**
 * Perform audio language detection inference
 */
export const performAudioLanguageDetectionInference = async (
  audioContent: string,
  serviceId: string
): Promise<{ data: AudioLanguageDetectionInferenceResponse; responseTime: number }> => {
  try {
    const payload: AudioLanguageDetectionInferenceRequest = {
      audio: [{ audioContent }],
      config: {
        serviceId,
      },
    };

    const response = await apiClient.post<AudioLanguageDetectionInferenceResponse>(
      apiEndpoints['audio-language-detection'].inference,
      payload
    );

    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('Audio language detection inference error:', error);
    throw error; // Re-throw so toast can show backend message via extractErrorInfo
  }
};

