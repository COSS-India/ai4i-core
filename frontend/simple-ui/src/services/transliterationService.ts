// Transliteration service API client

import { apiClient, apiEndpoints } from './api';

export interface TransliterationInferenceRequest {
  input: Array<{
    source: string;
  }>;
  config: {
    serviceId: string;
    language: {
      sourceLanguage: string;
      targetLanguage: string;
      sourceScriptCode?: string;
      targetScriptCode?: string;
    };
    isSentence?: boolean;
    numSuggestions?: number;
  };
  controlConfig?: {
    [key: string]: any;
  };
}

export interface TransliterationInferenceResponse {
  output: Array<{
    source: string;
    target: string;
    [key: string]: any;
  }>;
}

/**
 * Perform transliteration inference
 */
export const performTransliterationInference = async (
  text: string,
  config: TransliterationInferenceRequest['config']
): Promise<{ data: TransliterationInferenceResponse; responseTime: number }> => {
  try {
    const payload: TransliterationInferenceRequest = {
      input: [{ source: text }],
      config: {
        ...config,
        isSentence: config.isSentence ?? true,
        numSuggestions: config.numSuggestions ?? 0,
      },
    };

    const response = await apiClient.post<TransliterationInferenceResponse>(
      apiEndpoints.transliteration.inference,
      payload
    );

    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('Transliteration inference error:', error);
    throw new Error('Failed to perform transliteration inference');
  }
};

