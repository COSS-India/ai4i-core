// ASR service API client with typed methods

import { apiClient, apiEndpoints } from './api';
import { 
  ASRInferenceRequest, 
  ASRInferenceResponse, 
  ASRModel, 
  ASRHealthResponse,
  ASRModelsResponse 
} from '../types/asr';

/**
 * Perform ASR inference on audio content
 * @param audioContent - Base64 encoded audio content
 * @param config - ASR configuration
 * @returns Promise with ASR inference response
 */
export const performASRInference = async (
  audioContent: string,
  config: ASRInferenceRequest['config']
): Promise<ASRInferenceResponse> => {
  try {
    const payload: ASRInferenceRequest = {
      audio: [{ audioContent }],
      config,
      controlConfig: {
        dataTracking: false,
      },
    };

    const response = await apiClient.post<ASRInferenceResponse>(
      apiEndpoints.asr.inference,
      payload
    );

    return response.data;
  } catch (error) {
    console.error('ASR inference error:', error);
    throw new Error('Failed to perform ASR inference');
  }
};

/**
 * Get list of available ASR models
 * @returns Promise with ASR models response
 */
export const listASRModels = async (): Promise<ASRModelsResponse> => {
  try {
    const response = await apiClient.get<ASRModelsResponse>(
      apiEndpoints.asr.models
    );

    return response.data;
  } catch (error) {
    console.error('Failed to fetch ASR models:', error);
    throw new Error('Failed to fetch ASR models');
  }
};

/**
 * Check ASR service health
 * @returns Promise with health status
 */
export const checkASRHealth = async (): Promise<ASRHealthResponse> => {
  try {
    const response = await apiClient.get<ASRHealthResponse>(
      apiEndpoints.asr.health
    );

    return response.data;
  } catch (error) {
    console.error('Failed to check ASR health:', error);
    throw new Error('Failed to check ASR service health');
  }
};

/**
 * Get ASR service configuration
 * @returns Promise with service configuration
 */
export const getASRConfig = async () => {
  try {
    const response = await apiClient.get('/api/v1/asr/config');
    return response.data;
  } catch (error) {
    console.error('Failed to fetch ASR config:', error);
    throw new Error('Failed to fetch ASR configuration');
  }
};

/**
 * Validate ASR request before sending
 * @param audioContent - Base64 encoded audio content
 * @param config - ASR configuration
 * @returns Validation result
 */
export const validateASRRequest = (
  audioContent: string,
  config: ASRInferenceRequest['config']
): { isValid: boolean; error?: string } => {
  if (!audioContent || audioContent.trim() === '') {
    return { isValid: false, error: 'Audio content is required' };
  }

  if (!config.language.sourceLanguage) {
    return { isValid: false, error: 'Source language is required' };
  }

  if (!config.serviceId) {
    return { isValid: false, error: 'Service ID is required' };
  }

  if (!config.audioFormat) {
    return { isValid: false, error: 'Audio format is required' };
  }

  if (!config.samplingRate || config.samplingRate <= 0) {
    return { isValid: false, error: 'Valid sampling rate is required' };
  }

  return { isValid: true };
};
