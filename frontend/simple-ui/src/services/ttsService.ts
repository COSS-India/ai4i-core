// TTS service API client with typed methods

import { apiService, apiEndpoints } from './api';
import {
  inferenceConfigJsonSchema,
  ttsHealthResponseSchema,
  ttsInferenceResponseSchema,
  voiceListResponseSchema,
  voiceSchema,
} from './dto/schemas/inference';
import {
  TTSInferenceRequest,
  TTSInferenceResponse,
  Voice,
  TTSHealthResponse,
  VoiceListResponse,
  VoiceFilterOptions
} from '../types/tts';
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

export interface TTSServiceDetailsResponse {
  service_id: string;
  model_id: string;
  model_version: string;
  name: string;
  serviceDescription: string;
  endpoint: string;
  supported_languages: string[];
}

/**
 * Get list of available TTS services from model management service
 * @returns Promise with TTS services response
 */
export const listTTSServices = async (): Promise<TTSServiceDetailsResponse[]> => {
  try {
    // Fetch services from model management service filtered by task_type='tts'
    const services = await listServices('tts', true);
    const seen = new Set<string>();

    // Transform model management service response to TTSServiceDetailsResponse format
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
      } as TTSServiceDetailsResponse;
    });

    // Deduplicate by service_id in case API returns duplicates
    const uniqueServices: TTSServiceDetailsResponse[] = [];
    for (const svc of normalized) {
      if (!svc.service_id) continue;
      if (seen.has(svc.service_id)) continue;
      seen.add(svc.service_id);
      uniqueServices.push(svc);
    }

    return uniqueServices;
  } catch (error) {
    console.error('Failed to fetch TTS services:', error);
    throw new Error('Failed to fetch TTS services');
  }
};

/**
 * Perform TTS inference on text
 * @param text - Text to synthesize
 * @param config - TTS configuration
 * @returns Promise with TTS inference response and timing info
 */
export const performTTSInference = async (
  text: string,
  config: TTSInferenceRequest['config']
): Promise<{ data: TTSInferenceResponse; responseTime: number }> => {
  try {
    const payload: TTSInferenceRequest = {
      input: [{ source: text }],
      config,
      controlConfig: {
        dataTracking: false,
      },
    };

    const response = await apiService.post(apiEndpoints.tts.inference, payload, {
      responseSchema: ttsInferenceResponseSchema,
    });

    // Extract response time from headers
    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('TTS inference error:', error);
    throw error; // Re-throw so toast can show backend message via extractErrorInfo
  }
};

/**
 * Get list of available voices
 * @param filters - Optional filters for voices
 * @returns Promise with voice list response
 */
export const listVoices = async (filters?: VoiceFilterOptions): Promise<VoiceListResponse> => {
  try {
    const params: Record<string, any> = {};

    if (filters?.language) {
      params.language = filters.language;
    }
    if (filters?.gender) {
      params.gender = filters.gender;
    }
    if (filters?.age) {
      params.age = filters.age;
    }
    if (filters?.isActive !== undefined) {
      params.is_active = filters.isActive;
    }

    const response = await apiService.get(apiEndpoints.tts.voices, {
      params,
      timeout: 15000,
      responseSchema: voiceListResponseSchema,
    });

    return response.data;
  } catch (error) {
    console.error('Failed to fetch voices:', error);
    throw new Error('Failed to fetch available voices');
  }
};

/**
 * Check TTS service health
 * @returns Promise with health status
 */
export const checkTTSHealth = async (): Promise<TTSHealthResponse> => {
  try {
    const response = await apiService.get(apiEndpoints.tts.health, {
      responseSchema: ttsHealthResponseSchema,
    });

    return response.data;
  } catch (error) {
    console.error('Failed to check TTS health:', error);
    throw new Error('Failed to check TTS service health');
  }
};

/**
 * Get TTS service configuration
 * @returns Promise with service configuration
 */
export const getTTSConfig = async () => {
  try {
    const response = await apiService.get(apiEndpoints.tts.config, {
      responseSchema: inferenceConfigJsonSchema,
    });
    return response.data;
  } catch (error) {
    console.error('Failed to fetch TTS config:', error);
    throw new Error('Failed to fetch TTS configuration');
  }
};

/**
 * Get voice details by ID
 * @param voiceId - Voice ID
 * @returns Promise with voice details
 */
export const getVoiceById = async (voiceId: string): Promise<Voice> => {
  try {
    const response = await apiService.get(`${apiEndpoints.tts.voices}/${voiceId}`, {
      responseSchema: voiceSchema,
    });
    return response.data;
  } catch (error) {
    console.error('Failed to fetch voice details:', error);
    throw new Error('Failed to fetch voice details');
  }
};

/**
 * Validate TTS request before sending
 * @param text - Text to synthesize
 * @param config - TTS configuration
 * @returns Validation result
 */
export const validateTTSRequest = (
  text: string,
  config: TTSInferenceRequest['config']
): { isValid: boolean; error?: string } => {
  if (!text || text.trim() === '') {
    return { isValid: false, error: 'Text input is required' };
  }

  if (text.length > 512) {
    return { isValid: false, error: 'Text length exceeds maximum limit of 512 characters' };
  }

  if (!config.language.sourceLanguage) {
    return { isValid: false, error: 'Source language is required' };
  }

  if (!config.serviceId) {
    return { isValid: false, error: 'Service ID is required' };
  }

  if (!config.gender) {
    return { isValid: false, error: 'Gender is required' };
  }

  if (!config.audioFormat) {
    return { isValid: false, error: 'Audio format is required' };
  }

  if (!config.samplingRate || config.samplingRate <= 0) {
    return { isValid: false, error: 'Valid sampling rate is required' };
  }

  return { isValid: true };
};

/**
 * Get supported languages for TTS
 * @returns Promise with supported languages
 */
export const getSupportedLanguages = async (): Promise<string[]> => {
  try {
    const voices = await listVoices();
    const languages = new Set<string>();

    voices.voices.forEach(voice => {
      voice.languages.forEach(lang => languages.add(lang));
    });

    return Array.from(languages);
  } catch (error) {
    console.error('Failed to fetch supported languages:', error);
    throw new Error('Failed to fetch supported languages');
  }
};
