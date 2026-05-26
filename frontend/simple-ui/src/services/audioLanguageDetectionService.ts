// Audio Language Detection service API client

import { apiService, apiEndpoints } from './api';
import { audioLanguageDetectionInferenceResponseSchema } from './dto/schemas/inference';
import { listServices } from './modelManagementService';
import type { Service } from '../types/platform';
import {
  extractLanguageCodes,
  resolveEndpoint,
  resolveModelId,
  resolveModelVersion,
  resolveServiceId,
} from '../utils/platformService';

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
    const services = await listServices('audio-lang-detection', true);

    // Transform to AudioLanguageDetectionServiceDetailsResponse format
    const transformedServices = services.map((service: Service) => {
      const supportedLanguages = extractLanguageCodes(service.languages, 'simple');
      const endpoint = resolveEndpoint(service);

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

    const response = await apiService.post(
      apiEndpoints['audio-language-detection'].inference,
      payload,
      { responseSchema: audioLanguageDetectionInferenceResponseSchema }
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
