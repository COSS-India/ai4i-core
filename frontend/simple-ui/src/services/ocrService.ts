// OCR service API client

import { apiService, apiEndpoints } from './api';
import { ocrInferenceResponseSchema } from './dto/schemas/inference';
import { listServices } from './modelManagementService';
import type { Service } from '../types/platform';
import {
  extractLanguageCodes,
  resolveEndpoint,
  resolveModelId,
  resolveModelVersion,
  resolveServiceId,
  stripEndpointProtocol,
} from '../utils/platformService';

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

export interface OCRServiceDetailsResponse {
  service_id: string;
  model_id: string;
  model_version: string;
  name: string;
  serviceDescription: string;
  endpoint: string;
  supported_languages: string[];
}

/**
 * Get list of available OCR services from model management service
 * @returns Promise with OCR services response
 */
export const listOCRServices = async (): Promise<OCRServiceDetailsResponse[]> => {
  try {
    // Fetch services from model management service filtered by task_type='ocr'
    const services = await listServices('ocr', true);
    const seen = new Set<string>();

    // Transform model management service response to OCRServiceDetailsResponse format
    const normalized = services.map((service: Service) => {
      const supportedLanguages = extractLanguageCodes(service.languages, 'simple');
      const endpoint = stripEndpointProtocol(resolveEndpoint(service));

      return {
        service_id: resolveServiceId(service),
        model_id: resolveModelId(service),
        model_version: resolveModelVersion(service),
        name: service.name || resolveServiceId(service),
        serviceDescription: service.serviceDescription || service.description || '',
        endpoint,
        supported_languages: supportedLanguages,
      } as OCRServiceDetailsResponse;
    });

    // Deduplicate by service_id in case API returns duplicates
    const uniqueServices: OCRServiceDetailsResponse[] = [];
    for (const svc of normalized) {
      if (!svc.service_id) continue;
      if (seen.has(svc.service_id)) continue;
      seen.add(svc.service_id);
      uniqueServices.push(svc);
    }

    return uniqueServices;
  } catch (error) {
    console.error('Failed to fetch OCR services:', error);
    throw new Error('Failed to fetch OCR services');
  }
};

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

    const response = await apiService.post(apiEndpoints.ocr.inference, payload, {
      responseSchema: ocrInferenceResponseSchema,
    });

    const responseTime = parseInt(response.headers['request-duration'] || '0');

    return {
      data: response.data,
      responseTime
    };
  } catch (error) {
    console.error('OCR inference error:', error);
    throw error; // Re-throw so toast can show backend message via extractErrorInfo
  }
};
