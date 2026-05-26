// Speaker Diarization service API client

import { apiService, apiEndpoints } from './api';
import { speakerDiarizationInferenceResponseSchema } from './dto/schemas/inference';
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

export interface SpeakerDiarizationServiceDetailsResponse {
  service_id: string;
  model_id: string;
  model_version: string;
  name: string;
  serviceDescription: string;
  endpoint: string;
  supported_languages: string[];
}

export interface SpeakerDiarizationInferenceRequest {
  audio: Array<{
    audioContent: string;
  }>;
  config: {
    serviceId: string;
    [key: string]: any;
  };
}

export interface SpeakerDiarizationInferenceResponse {
  output: Array<{
    segments?: Array<{
      start: number;
      end: number;
      speaker: string;
      text?: string;
    }>;
    [key: string]: any;
  }>;
}

/**
 * Get list of available Speaker Diarization services from model management service
 * @returns Promise with Speaker Diarization services response
 */
export const listSpeakerDiarizationServices = async (): Promise<SpeakerDiarizationServiceDetailsResponse[]> => {
  try {
    // Fetch services from model management service filtered by task_type='speaker-diarization'
    const services = await listServices('speaker-diarization', true);
    const seen = new Set<string>();

    // Transform model management service response to SpeakerDiarizationServiceDetailsResponse format
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
      } as SpeakerDiarizationServiceDetailsResponse;
    });

    // Deduplicate by service_id in case API returns duplicates
    const uniqueServices: SpeakerDiarizationServiceDetailsResponse[] = [];
    for (const svc of normalized) {
      if (!svc.service_id) continue;
      if (seen.has(svc.service_id)) continue;
      seen.add(svc.service_id);
      uniqueServices.push(svc);
    }

    return uniqueServices;
  } catch (error) {
    console.error('Failed to fetch Speaker Diarization services:', error);
    throw new Error('Failed to fetch Speaker Diarization services');
  }
};

/**
 * Perform speaker diarization inference
 */
export const performSpeakerDiarizationInference = async (
  audioContent: string,
  serviceId: string
): Promise<{ data: SpeakerDiarizationInferenceResponse; responseTime: number }> => {
  try {
    const payload: SpeakerDiarizationInferenceRequest = {
      audio: [{ audioContent }],
      config: {
        serviceId,
      },
    };

    const response = await apiService.post(
      apiEndpoints['speaker-diarization'].inference,
      payload,
      { responseSchema: speakerDiarizationInferenceResponseSchema }
    );

    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('Speaker diarization inference error:', error);
    throw error; // Re-throw so toast can show backend message via extractErrorInfo
  }
};
