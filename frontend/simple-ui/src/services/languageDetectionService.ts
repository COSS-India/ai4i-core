// Language Detection service API client

import { apiClient, apiEndpoints } from './api';

export interface LanguageDetectionInferenceRequest {
  input: Array<{
    source: string;
  }>;
  config: {
    serviceId: string;
  };
}

export interface LanguagePrediction {
  langCode: string;
  scriptCode: string;
  langScore: number;
  language: string;
}

export interface LanguageDetectionInferenceResponse {
  output: Array<{
    source: string;
    langPrediction: LanguagePrediction[];
    [key: string]: any;
  }>;
}

/**
 * Perform language detection inference
 */
export const performLanguageDetectionInference = async (
  texts: string[],
  serviceId: string
): Promise<{ data: LanguageDetectionInferenceResponse; responseTime: number }> => {
  try {
    const payload: LanguageDetectionInferenceRequest = {
      input: texts.map(text => ({ source: text })),
      config: {
        serviceId,
      },
    };

    const response = await apiClient.post<LanguageDetectionInferenceResponse>(
      apiEndpoints['language-detection'].inference,
      payload
    );

    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('Language detection inference error:', error);
    throw new Error('Failed to perform language detection inference');
  }
};

