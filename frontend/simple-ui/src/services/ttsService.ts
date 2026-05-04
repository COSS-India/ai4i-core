// TTS service API client with typed methods

import { apiClient, apiEndpoints } from './api';
import { 
  TTSInferenceRequest, 
  TTSInferenceResponse, 
  Voice, 
  TTSHealthResponse,
  VoiceListResponse,
  VoiceFilterOptions
} from '../types/tts';
import { listServices } from './modelManagementService';

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

    const response = await apiClient.post<TTSInferenceResponse>(
      apiEndpoints.tts.inference,
      payload
    );

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

    const response = await apiClient.get<VoiceListResponse>(
      apiEndpoints.tts.voices,
      { params, timeout: 15000 }
    );

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
    const response = await apiClient.get<TTSHealthResponse>(
      apiEndpoints.tts.health
    );

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
    const response = await apiClient.get('/api/v1/tts/config');
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
    const response = await apiClient.get<Voice>(`${apiEndpoints.tts.voices}/${voiceId}`);
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
