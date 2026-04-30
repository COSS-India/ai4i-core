// NER service API client

import { apiClient, apiEndpoints } from './api';
import { listServices } from './modelManagementService';

export interface NERServiceDetailsResponse {
  service_id: string;
  model_id: string;
  model_version: string;
  name: string;
  serviceDescription: string;
  endpoint: string;
  supported_languages: string[];
}

export interface NERInferenceRequest {
  input: Array<{
    source: string;
  }>;
  config: {
    serviceId: string;
    language: {
      sourceLanguage: string;
    };
  };
}

export interface NERInferenceResponse {
  output: Array<{
    source: string;
    entities?: Array<{
      text: string;
      label: string;
      start: number;
      end: number;
    }>;
    [key: string]: any;
  }>;
}

/**
 * List all available NER services
 */
export const listNERServices = async (): Promise<NERServiceDetailsResponse[]> => {
  try {
    const services = await listServices('ner');
    
    // Transform to NERServiceDetailsResponse format
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
    console.error('Failed to fetch NER services:', error);
    throw new Error('Failed to fetch NER services');
  }
};

/**
 * Perform NER inference
 */
export const performNERInference = async (
  text: string,
  config: NERInferenceRequest['config']
): Promise<{ data: NERInferenceResponse; responseTime: number }> => {
  try {
    const payload: NERInferenceRequest = {
      input: [{ source: text }],
      config,
    };

    const response = await apiClient.post<NERInferenceResponse>(
      apiEndpoints.ner.inference,
      payload
    );

    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('NER inference error:', error);
    throw new Error('Failed to perform NER inference');
  }
};

