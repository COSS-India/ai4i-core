// OCR service API client

import { apiClient, apiEndpoints } from './api';
import { listServices } from './modelManagementService';

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
    const services = await listServices('ocr');
    const seen = new Set<string>();

    // Transform model management service response to OCRServiceDetailsResponse format
    const normalized = services.map((service: any) => {
      // Extract languages from service.languages array
      const supportedLanguages: string[] = [];
      if (service.languages && Array.isArray(service.languages)) {
        service.languages.forEach((lang: any) => {
          if (typeof lang === 'string') {
            supportedLanguages.push(lang);
          } else if (lang && typeof lang === 'object') {
            // Handle different language object formats
            const langCode = lang.code || lang.language;
            if (langCode) {
              supportedLanguages.push(langCode);
            }
          }
        });
      }
      
      // Extract endpoint and clean it
      let endpoint = service.endpoint || '';
      if (endpoint) {
        endpoint = endpoint.replace('http://', '').replace('https://', '');
      }
      
      return {
        service_id: service.serviceId || service.service_id,
        model_id: service.modelId || service.model_id,
        model_version: service.modelVersion || service.model_version || '',
        name: service.name || service.serviceId || '',
        serviceDescription: service.serviceDescription || service.description || '',
        endpoint: endpoint,
        supported_languages: Array.from(new Set(supportedLanguages)), // Remove duplicates
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

