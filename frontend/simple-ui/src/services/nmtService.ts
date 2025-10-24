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
