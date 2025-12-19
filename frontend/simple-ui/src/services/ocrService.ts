// OCR service API client

import { apiClient, apiEndpoints } from './api';

export interface OCRInferenceRequest {
  image: Array<{
    imageContent?: string | null;
    imageUri?: string | null;
  }>;
  config: {
    serviceId: string;
    language: {
      sourceLanguage: string;
      sourceScriptCode?: string;
    };
    textDetection?: boolean;
  };
  controlConfig?: {
    dataTracking?: boolean;
  };
}

export interface OCRInferenceResponse {
  output: Array<{
    source: string;
    [key: string]: any;
  }>;
}

/**
 * Perform OCR inference on image
 */
export const performOCRInference = async (
  imageContent: string | null,
  imageUri: string | null,
  config: OCRInferenceRequest['config']
): Promise<{ data: OCRInferenceResponse; responseTime: number }> => {
  try {
    const payload: OCRInferenceRequest = {
      image: [{
        imageContent: imageContent,
        imageUri: imageUri,
      }],
      config: {
        ...config,
        textDetection: config.textDetection ?? true,
      },
      controlConfig: {
        dataTracking: true,
      },
    };

    const response = await apiClient.post<OCRInferenceResponse>(
      apiEndpoints.ocr.inference,
      payload
    );

    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('OCR inference error:', error);
    throw new Error('Failed to perform OCR inference');
  }
};

