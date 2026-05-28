// NER service API client

import { apiService, apiEndpoints } from './api';
import { nerInferenceResponseSchema } from './dto/schemas/inference';
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
    const services = await listServices('ner', true);

    // Transform to NERServiceDetailsResponse format
    const transformedServices = services.map((service: Service) => {
      const supportedLanguages = extractLanguageCodes(service.languages, 'simple');
      const endpoint = stripEndpointProtocol(resolveEndpoint(service));

      return {
        service_id: resolveServiceId(service),
        model_id: resolveModelId(service),
        model_version: resolveModelVersion(service),
        name: service.name || resolveServiceId(service),
        serviceDescription: service.serviceDescription || service.description || 'No description available',
        endpoint,
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

    const response = await apiService.post(apiEndpoints.ner.inference, payload, {
      responseSchema: nerInferenceResponseSchema,
    });

    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('NER inference error:', error);
    throw error; // Re-throw so toast can show backend message via extractErrorInfo
  }
};
