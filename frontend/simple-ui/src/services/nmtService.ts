// NMT service API client with typed methods

import { apiClient, apiEndpoints } from './api';
import { 
  NMTInferenceRequest, 
  NMTInferenceResponse, 
  NMTModel, 
  NMTHealthResponse,
  NMTModelsResponse,
  NMTLanguagesResponse,
  NMTModelDetailsResponse,
  NMTServiceDetailsResponse,
  LanguagePair
} from '../types/nmt';

/**
 * Perform NMT inference on text
 * @param text - Text to translate
 * @param config - NMT configuration
 * @returns Promise with NMT inference response and timing info
 */
export const performNMTInference = async (
  text: string,
  config: NMTInferenceRequest['config']
): Promise<{ data: NMTInferenceResponse; responseTime: number }> => {
  try {
    const payload: NMTInferenceRequest = {
      input: [{ source: text }],
      config,
      controlConfig: {
        dataTracking: false,
      },
    };

    const response = await apiClient.post<NMTInferenceResponse>(
      apiEndpoints.nmt.inference,
      payload
    );

    // Extract response time from headers
    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('NMT inference error:', error);
    throw new Error('Failed to perform NMT inference');
  }
};

/**
 * Get list of available NMT models
 * @returns Promise with NMT models response
 */
export const listNMTModels = async (): Promise<NMTModelDetailsResponse[]> => {
  try {
    const response = await apiClient.get<{ models: NMTModelDetailsResponse[]; total_models: number }>(
      apiEndpoints.nmt.models
    );

    return response.data.models;
  } catch (error) {
    console.error('Failed to fetch NMT models:', error);
    throw new Error('Failed to fetch NMT models');
  }
};

/**
 * Get list of available NMT services
 * @returns Promise with NMT services response
 */
export const listNMTServices = async (): Promise<NMTServiceDetailsResponse[]> => {
  try {
    const response = await apiClient.get<{ services: NMTServiceDetailsResponse[]; total_services: number }>(
      apiEndpoints.nmt.services
    );

    return response.data.services;
  } catch (error) {
    console.error('Failed to fetch NMT services:', error);
    throw new Error('Failed to fetch NMT services');
  }
};

/**
 * Get supported languages for a specific NMT model
 * @param modelId - Model ID to get languages for
 * @returns Promise with NMT languages response
 */
export const getNMTLanguages = async (modelId?: string): Promise<NMTLanguagesResponse> => {
  try {
    const url = modelId 
      ? `${apiEndpoints.nmt.languages}?model_id=${encodeURIComponent(modelId)}`
      : apiEndpoints.nmt.languages;
    
    const response = await apiClient.get<NMTLanguagesResponse>(url);

    return response.data;
  } catch (error) {
    console.error('Failed to fetch NMT languages:', error);
    throw new Error('Failed to fetch NMT languages');
  }
};

/**
 * Get supported languages for a specific NMT service
 * @param serviceId - Service ID to get languages for
 * @returns Promise with NMT languages response
 */
export const getNMTLanguagesForService = async (
  serviceId: string
): Promise<NMTLanguagesResponse | null> => {
  try {
    // Call /languages endpoint with service_id parameter
    const url = `${apiEndpoints.nmt.languages}?service_id=${encodeURIComponent(serviceId)}`;
    const response = await apiClient.get<NMTLanguagesResponse>(url);
    return response.data;
  } catch (error) {
    console.error('Failed to fetch NMT languages for service:', error);
    throw new Error('Failed to fetch NMT languages for service');
  }
};

/**
 * Check NMT service health
 * @returns Promise with health status
 */
export const checkNMTHealth = async (): Promise<NMTHealthResponse> => {
  try {
    const response = await apiClient.get<NMTHealthResponse>(
      apiEndpoints.nmt.health
    );

    return response.data;
  } catch (error) {
    console.error('Failed to check NMT health:', error);
    throw new Error('Failed to check NMT service health');
  }
};

/**
 * Get NMT service configuration
 * @returns Promise with service configuration
 */
export const getNMTConfig = async () => {
  try {
    const response = await apiClient.get('/api/v1/nmt/config');
    return response.data;
  } catch (error) {
    console.error('Failed to fetch NMT config:', error);
    throw new Error('Failed to fetch NMT configuration');
  }
};

/**
 * Get supported language pairs for a specific model
 * @param modelId - Model ID to get language pairs for
 * @returns Promise with supported language pairs
 */
export const getSupportedLanguagePairs = async (modelId?: string): Promise<LanguagePair[]> => {
  try {
    const languagesResponse = await getNMTLanguages(modelId);
    const languagePairs: LanguagePair[] = [];
    
    // Generate all possible language pairs from supported languages
    const supportedLanguages = languagesResponse.supported_languages;
    
    for (let i = 0; i < supportedLanguages.length; i++) {
      for (let j = 0; j < supportedLanguages.length; j++) {
        if (i !== j) {
          languagePairs.push({
            sourceLanguage: supportedLanguages[i],
            targetLanguage: supportedLanguages[j],
          });
        }
      }
    }
    
    return languagePairs;
  } catch (error) {
    console.error('Failed to fetch supported language pairs:', error);
    throw new Error('Failed to fetch supported language pairs');
  }
};

/**
 * Get supported language pairs for a specific service
 * @param serviceId - Service ID to get language pairs for
 * @param services - List of services to look up
 * @returns Promise with supported language pairs
 */
export const getSupportedLanguagePairsForService = async (
  serviceId: string,
  services: NMTServiceDetailsResponse[]
): Promise<LanguagePair[]> => {
  try {
    const service = services.find(s => s.service_id === serviceId);
    if (!service) {
      return [];
    }
    
    // If service has explicit language pairs, use those
    if (service.supported_language_pairs && service.supported_language_pairs.length > 0) {
      return service.supported_language_pairs.map(pair => ({
        sourceLanguage: pair.sourceLanguage,
        targetLanguage: pair.targetLanguage,
        sourceScriptCode: pair.sourceScriptCode,
        targetScriptCode: pair.targetScriptCode,
      }));
    }
    
    // Otherwise, get from model
    return getSupportedLanguagePairs(service.model_id);
  } catch (error) {
    console.error('Failed to fetch supported language pairs for service:', error);
    throw new Error('Failed to fetch supported language pairs for service');
  }
};

/**
 * Validate NMT request before sending
 * @param text - Text to translate
 * @param config - NMT configuration
 * @returns Validation result
 */
export const validateNMTRequest = (
  text: string,
  config: NMTInferenceRequest['config']
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

  if (!config.language.targetLanguage) {
    return { isValid: false, error: 'Target language is required' };
  }

  if (config.language.sourceLanguage === config.language.targetLanguage) {
    return { isValid: false, error: 'Source and target languages must be different' };
  }

  if (!config.serviceId) {
    return { isValid: false, error: 'Service ID is required' };
  }

  return { isValid: true };
};

/**
 * Get model by language pair
 * @param languagePair - Source and target language pair
 * @returns Promise with matching model
 */
export const getModelByLanguagePair = async (
  languagePair: LanguagePair
): Promise<NMTModelDetailsResponse | null> => {
  try {
    const models = await listNMTModels();
    
    const matchingModel = models.find(model =>
      model.supported_languages.includes(languagePair.sourceLanguage) &&
      model.supported_languages.includes(languagePair.targetLanguage)
    );
    
    return matchingModel || null;
  } catch (error) {
    console.error('Failed to find model for language pair:', error);
    throw new Error('Failed to find model for language pair');
  }
};

/**
 * Get service by language pair
 * @param languagePair - Source and target language pair
 * @returns Promise with matching service
 */
export const getServiceByLanguagePair = async (
  languagePair: LanguagePair
): Promise<NMTServiceDetailsResponse | null> => {
  try {
    const services = await listNMTServices();
    
    const matchingService = services.find(service =>
      service.supported_languages.includes(languagePair.sourceLanguage) &&
      service.supported_languages.includes(languagePair.targetLanguage)
    );
    
    return matchingService || null;
  } catch (error) {
    console.error('Failed to find service for language pair:', error);
    throw new Error('Failed to find service for language pair');
  }
};

/**
 * Check if language pair is supported
 * @param languagePair - Source and target language pair
 * @returns Promise with support status
 */
export const isLanguagePairSupported = async (
  languagePair: LanguagePair
): Promise<boolean> => {
  try {
    const model = await getModelByLanguagePair(languagePair);
    return model !== null;
  } catch (error) {
    console.error('Failed to check language pair support:', error);
    return false;
  }
};
