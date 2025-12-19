// NER service API client

import { apiClient, apiEndpoints } from './api';

export interface NERInferenceRequest {
  input: Array<{
    source: string;
  }>;
  config: {
    serviceId: string;
    language: {
      sourceLanguage: string;
    };
  };
}

export interface NERInferenceResponse {
  output: Array<{
    source: string;
    entities?: Array<{
      text: string;
      label: string;
      start: number;
      end: number;
    }>;
    [key: string]: any;
  }>;
}

/**
 * Perform NER inference
 */
export const performNERInference = async (
  text: string,
  config: NERInferenceRequest['config']
): Promise<{ data: NERInferenceResponse; responseTime: number }> => {
  try {
    const payload: NERInferenceRequest = {
      input: [{ source: text }],
      config,
    };

    const response = await apiClient.post<NERInferenceResponse>(
      apiEndpoints.ner.inference,
      payload
    );

    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('NER inference error:', error);
    throw new Error('Failed to perform NER inference');
  }
};

