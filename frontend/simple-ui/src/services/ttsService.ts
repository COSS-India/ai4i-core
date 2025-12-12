// TTS service API client with typed methods

import { apiClient, apiEndpoints } from './api';
import { listServices } from './modelManagementService';
import { 
  TTSInferenceRequest, 
  TTSInferenceResponse, 
  Voice, 
  TTSHealthResponse,
  VoiceListResponse,
  VoiceFilterOptions,
  TTSServiceDetailsResponse,
  TTSLanguagesResponse
} from '../types/tts';

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
    throw new Error('Failed to perform TTS inference');
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
      { params }
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

/**
 * Get list of available TTS services from model management service
 * @returns Promise with TTS services response
 */
export const listTTSServices = async (): Promise<TTSServiceDetailsResponse[]> => {
  try {
    // Fetch services from model management service filtered by task_type='tts'
    const services = await listServices('tts');
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
            const langCode = lang.code || lang.sourceLanguage || lang.language;
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
        triton_endpoint: endpoint,
        triton_model: 'tts', // Default value
        provider: service.name || service.serviceId || 'unknown', // Keep for backward compatibility
        description: service.serviceDescription || service.description || '', // Keep for backward compatibility
        name: service.name || '',
        serviceDescription: service.serviceDescription || service.description || '',
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
 * Get supported languages for a specific TTS service from model management service
 * @param serviceId - Service ID to get languages for
 * @returns Promise with TTS languages response
 */
export const getTTSLanguagesForService = async (
  serviceId: string
): Promise<TTSLanguagesResponse | null> => {
  try {
    // Fetch all TTS services from model management service
    const services = await listServices('tts');
    
    // Find the service by serviceId
    const service = services.find((s: any) => 
      (s.serviceId || s.service_id) === serviceId
    );
    
    if (!service) {
      console.warn(`Service ${serviceId} not found`);
      return null;
    }
    
    // Extract languages from service.languages array
    const supportedLanguages: string[] = [];
    const languageDetails: Array<{code: string; name: string}> = [];
    
    if (service.languages && Array.isArray(service.languages)) {
      service.languages.forEach((lang: any) => {
        if (typeof lang === 'string') {
          supportedLanguages.push(lang);
          languageDetails.push({ code: lang, name: lang });
        } else if (lang && typeof lang === 'object') {
          // Handle different language object formats
          const langCode = lang.code || lang.sourceLanguage || lang.language;
          const langName = lang.name || langCode;
          if (langCode) {
            supportedLanguages.push(langCode);
            languageDetails.push({ code: langCode, name: langName });
          }
        }
      });
    }
    
    // Remove duplicates
    const uniqueLanguages = Array.from(new Set(supportedLanguages));
    const uniqueLanguageDetails = languageDetails.filter((lang, index, self) =>
      index === self.findIndex((l) => l.code === lang.code)
    );
    
    return {
      model_id: service.modelId || service.model_id || '',
      provider: service.name || service.serviceId || 'unknown',
      supported_languages: uniqueLanguages,
      language_details: uniqueLanguageDetails,
      total_languages: uniqueLanguages.length,
    };
  } catch (error) {
    console.error('Failed to fetch TTS languages for service:', error);
    throw new Error('Failed to fetch TTS languages for service');
  }
};

/**
 * Get TTS service by language
 * @param language - Language code to find service for
 * @returns Promise with matching service
 */
export const getServiceByLanguage = async (
  language: string
): Promise<TTSServiceDetailsResponse | null> => {
  try {
    const services = await listTTSServices();
    
    const matchingService = services.find(service =>
      service.supported_languages.includes(language)
    );
    
    return matchingService || null;
  } catch (error) {
    console.error('Failed to find service for language:', error);
    throw new Error('Failed to find service for language');
  }
};

/**
 * Check if language is supported by any TTS service
 * @param language - Language code to check
 * @returns Promise with support status
 */
export const isLanguageSupported = async (language: string): Promise<boolean> => {
  try {
    const service = await getServiceByLanguage(language);
    return service !== null;
  } catch (error) {
    console.error('Failed to check language support:', error);
    return false;
  }
};
