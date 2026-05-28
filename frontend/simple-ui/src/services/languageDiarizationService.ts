// Language Diarization service API client

import { apiService, apiEndpoints } from './api';
import { languageDiarizationInferenceResponseSchema } from './dto/schemas/inference';
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
    const services = await listServices('language-diarization', true);
    const seen = new Set<string>();

    // Transform model management service response to LanguageDiarizationServiceDetailsResponse format
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

    const response = await apiService.post(
      apiEndpoints['language-diarization'].inference,
      payload,
      { responseSchema: languageDiarizationInferenceResponseSchema }
    );

    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('Language diarization inference error:', error);
    throw error; // Re-throw so toast can show backend message via extractErrorInfo
  }
};
