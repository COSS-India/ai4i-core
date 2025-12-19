// Audio Language Detection service API client

import { apiClient, apiEndpoints } from './api';

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

    const response = await apiClient.post<AudioLanguageDetectionInferenceResponse>(
      apiEndpoints['audio-language-detection'].inference,
      payload
    );

    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('Audio language detection inference error:', error);
    throw new Error('Failed to perform audio language detection inference');
  }
};

