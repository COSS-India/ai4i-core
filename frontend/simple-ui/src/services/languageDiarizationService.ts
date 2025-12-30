// Language Diarization service API client

import { apiClient, apiEndpoints } from './api';

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

    const response = await apiClient.post<LanguageDiarizationInferenceResponse>(
      apiEndpoints['language-diarization'].inference,
      payload
    );

    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('Language diarization inference error:', error);
    throw new Error('Failed to perform language diarization inference');
  }
};

