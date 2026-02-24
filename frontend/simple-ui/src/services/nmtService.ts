// NMT service API client with typed methods

import { apiClient, apiEndpoints } from './api';
import { listServices } from './modelManagementService';
import {
  NMTInferenceRequest,
  NMTInferenceResponse,
  NMTModel,
  NMTHealthResponse,
  NMTModelsResponse,
  NMTLanguagesResponse,
  NMTModelDetailsResponse,
  NMTServiceDetailsResponse,
  LanguagePair,
} from '../types/nmt';
import { performTryItNMTInference, trackTryItRequest } from './tryItService';
import { isAnonymousUser } from '../utils/anonymousSession';
import {
  INDICTRANS_ANONYMOUS_SERVICE_ID,
  INDICTRANS_ANONYMOUS_SERVICE,
} from '../data/indictransAnonymousService';
import { LANG_CODE_TO_LABEL } from '../config/constants';

/**
 * Perform NMT inference on text
 * Automatically uses try-it endpoint for anonymous users
 * @param text - Text to translate
 * @param config - NMT configuration
 * @param forceAuth - Force authenticated endpoint (for logged-in users)
 * @returns Promise with NMT inference response and timing info
 */
export const performNMTInference = async (
  text: string,
  config: NMTInferenceRequest['config'],
  forceAuth: boolean = false
): Promise<{ data: NMTInferenceResponse; responseTime: number }> => {
  try {
    // Check if user is anonymous and should use try-it endpoint
    const isAnonymous = isAnonymousUser();
    const useTryIt = isAnonymous && !forceAuth;

    if (useTryIt) {
      // Use try-it endpoint for anonymous users
      console.log('Using try-it endpoint for anonymous user');
      const result = await performTryItNMTInference(text, config);
      
      // Track request for client-side rate limit warning
      trackTryItRequest();
      
      return result;
    }

    // Use authenticated endpoint for logged-in users
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
    throw error;
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
 * Get hardcoded IndicTrans service for anonymous (try-it) users in NMTServiceDetailsResponse format.
 */
export const getIndicTransAnonymousService = (): NMTServiceDetailsResponse => {
  const pairs: LanguagePair[] = INDICTRANS_ANONYMOUS_SERVICE.languages.map((lang) => ({
    sourceLanguage: lang.sourceLanguage,
    targetLanguage: lang.targetLanguage,
  }));
  const codes = new Set<string>();
  INDICTRANS_ANONYMOUS_SERVICE.languages.forEach((lang) => {
    codes.add(lang.sourceLanguage);
    codes.add(lang.targetLanguage);
  });
  return {
    service_id: INDICTRANS_ANONYMOUS_SERVICE.serviceId,
    model_id: 'ai4bharat/indictrans-v2',
    model_version: 'v1',
    triton_endpoint: '',
    triton_model: 'nmt',
    provider: INDICTRANS_ANONYMOUS_SERVICE.name,
    description: INDICTRANS_ANONYMOUS_SERVICE.serviceDescription,
    name: INDICTRANS_ANONYMOUS_SERVICE.name,
    serviceDescription: INDICTRANS_ANONYMOUS_SERVICE.serviceDescription,
    supported_languages: Array.from(codes),
    supported_language_pairs: pairs,
    modelVersion: 'v1',
  };
};

/**
 * Get list of available NMT services from model management service
 * For anonymous users returns hardcoded IndicTrans service only.
 * For logged-in users returns only published services from Service Management
 * (if IndicTrans is in Service Management and published, it will appear here too).
 * @returns Promise with NMT services response
 */
export const listNMTServices = async (): Promise<NMTServiceDetailsResponse[]> => {
  if (isAnonymousUser()) {
    return [getIndicTransAnonymousService()];
  }
  try {
    // Logged-in users: only published services from Service Management
    const services = await listServices('nmt', true);
    const seen = new Set<string>();

    // Transform model management service response to NMTServiceDetailsResponse format
    const normalized = services.map((service: any) => {
      // Extract languages from service.languages array
      const supportedLanguages: string[] = [];
      if (service.languages && Array.isArray(service.languages)) {
        service.languages.forEach((lang: any) => {
          if (typeof lang === 'string') {
            supportedLanguages.push(lang);
          } else if (lang && typeof lang === 'object') {
            // Collect all codes from this entry (e.g. sourceLanguage + targetLanguage)
            const codes: string[] = [];
            if (lang.code) codes.push(lang.code);
            if (lang.sourceLanguage && !codes.includes(lang.sourceLanguage))
              codes.push(lang.sourceLanguage);
            if (lang.targetLanguage && !codes.includes(lang.targetLanguage))
              codes.push(lang.targetLanguage);
            if (lang.language && !codes.includes(lang.language)) codes.push(lang.language);
            codes.forEach((c) => supportedLanguages.push(c));
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
        triton_endpoint: endpoint,
        triton_model: 'nmt', // Default value
        provider: service.name || service.serviceId || 'unknown', // Keep for backward compatibility
        description: service.serviceDescription || service.description || '', // Keep for backward compatibility
        name: service.name || '',
        serviceDescription: service.serviceDescription || service.description || '',
        supported_languages: Array.from(new Set(supportedLanguages)), // Remove duplicates
        modelVersion: service.modelVersion || service.model_version,
      } as NMTServiceDetailsResponse;
    });

    // Deduplicate by service_id in case API returns duplicates
    const uniqueServices: NMTServiceDetailsResponse[] = [];
    for (const svc of normalized) {
      if (!svc.service_id) continue;
      if (seen.has(svc.service_id)) continue;
      seen.add(svc.service_id);
      uniqueServices.push(svc);
    }

    return uniqueServices;
  } catch (error) {
    console.error('Failed to fetch NMT services:', error);
    throw new Error('Failed to fetch NMT services');
  }
};

/**
 * Get supported languages for a specific NMT model from model management service
 * @param modelId - Model ID to get languages for
 * @returns Promise with NMT languages response
 */
export const getNMTLanguages = async (modelId?: string): Promise<NMTLanguagesResponse> => {
  try {
    // Fetch published NMT services from model management service
    const services = await listServices('nmt', true);

    // If modelId is provided, find a service with that modelId
    // Otherwise, use the first service
    let service: any;
    if (modelId) {
      service = services.find((s: any) => 
        (s.modelId || s.model_id) === modelId
      );
    } else if (services.length > 0) {
      service = services[0];
    }
    
    if (!service) {
      // Return empty response if no service found
      return {
        model_id: modelId || '',
        provider: 'unknown',
        supported_languages: [],
        language_details: [],
        total_languages: 0,
      };
    }
    
    // Extract languages from service.languages array
    const supportedLanguages: string[] = [];
    const languageDetails: Array<{code: string; name: string}> = [];
    
    if (service.languages && Array.isArray(service.languages)) {
      service.languages.forEach((lang: any) => {
        if (typeof lang === 'string') {
          supportedLanguages.push(lang);
          languageDetails.push({ code: lang, name: lang });
        } else if (lang && typeof lang === 'object') {
          // Handle different language object formats
          const langCode = lang.code || lang.sourceLanguage || lang.targetLanguage || lang.language;
          const langName = lang.name || langCode;
          if (langCode) {
            supportedLanguages.push(langCode);
            languageDetails.push({ code: langCode, name: langName });
          }
        }
      });
    }
    
    // Remove duplicates
    const uniqueLanguages = Array.from(new Set(supportedLanguages));
    const uniqueLanguageDetails = languageDetails.filter((lang, index, self) =>
      index === self.findIndex((l) => l.code === lang.code)
    );
    
    return {
      model_id: service.modelId || service.model_id || modelId || '',
      provider: service.name || service.serviceId || 'unknown',
      supported_languages: uniqueLanguages,
      language_details: uniqueLanguageDetails,
      total_languages: uniqueLanguages.length,
    };
  } catch (error) {
    console.error('Failed to fetch NMT languages:', error);
    throw new Error('Failed to fetch NMT languages');
  }
};

/**
 * Get supported languages for a specific NMT service from model management service.
 * For anonymous IndicTrans service returns hardcoded data.
 * @param serviceId - Service ID to get languages for
 * @returns Promise with NMT languages response
 */
export const getNMTLanguagesForService = async (
  serviceId: string
): Promise<NMTLanguagesResponse | null> => {
  if (serviceId === INDICTRANS_ANONYMOUS_SERVICE_ID) {
    const codes = new Set<string>();
    INDICTRANS_ANONYMOUS_SERVICE.languages.forEach((lang) => {
      codes.add(lang.sourceLanguage);
      codes.add(lang.targetLanguage);
    });
    const uniqueLanguages = Array.from(codes);
    const language_details = uniqueLanguages.map((code) => ({
      code,
      name: LANG_CODE_TO_LABEL[code] || code,
    }));
    return {
      model_id: 'ai4bharat/indictrans-v2',
      provider: INDICTRANS_ANONYMOUS_SERVICE.name,
      supported_languages: uniqueLanguages,
      language_details,
      total_languages: uniqueLanguages.length,
    };
  }
  try {
    // Fetch published NMT services from model management service
    const services = await listServices('nmt', true);

    // Find the service by serviceId
    const service = services.find((s: any) =>
      (s.serviceId || s.service_id) === serviceId
    );

    if (!service) {
      console.warn(`Service ${serviceId} not found`);
      return null;
    }

    // Extract languages from service.languages array
    const supportedLanguages: string[] = [];
    const languageDetails: Array<{ code: string; name: string }> = [];

    if (service.languages && Array.isArray(service.languages)) {
      service.languages.forEach((lang: any) => {
        if (typeof lang === 'string') {
          supportedLanguages.push(lang);
          languageDetails.push({ code: lang, name: lang });
        } else if (lang && typeof lang === 'object') {
          // Collect all language codes from this entry (e.g. sourceLanguage + targetLanguage)
          const codes: string[] = [];
          if (lang.code) codes.push(lang.code);
          if (lang.sourceLanguage && !codes.includes(lang.sourceLanguage))
            codes.push(lang.sourceLanguage);
          if (lang.targetLanguage && !codes.includes(lang.targetLanguage))
            codes.push(lang.targetLanguage);
          if (lang.language && !codes.includes(lang.language)) codes.push(lang.language);
          codes.forEach((langCode) => {
            supportedLanguages.push(langCode);
            const langName = lang.name || LANG_CODE_TO_LABEL[langCode] || langCode;
            languageDetails.push({ code: langCode, name: langName });
          });
        }
      });
    }

    const uniqueLanguages = Array.from(new Set(supportedLanguages));
    const uniqueLanguageDetails = languageDetails.filter((lang, index, self) =>
      index === self.findIndex((l) => l.code === lang.code)
    );

    return {
      model_id: service.modelId || service.model_id || '',
      provider: service.name || service.serviceId || 'unknown',
      supported_languages: uniqueLanguages,
      language_details: uniqueLanguageDetails,
      total_languages: uniqueLanguages.length,
    };
  } catch (error) {
    console.error('Failed to fetch NMT languages for service:', error);
    throw new Error('Failed to fetch NMT languages for service');
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
 * Get supported language pairs for a specific service
 * @param serviceId - Service ID to get language pairs for
 * @param services - List of services to look up
 * @returns Promise with supported language pairs
 */
export const getSupportedLanguagePairsForService = async (
  serviceId: string,
  services: NMTServiceDetailsResponse[]
): Promise<LanguagePair[]> => {
  try {
    const service = services.find(s => s.service_id === serviceId);
    if (!service) {
      return [];
    }
    
    // If service has explicit language pairs, use those
    if (service.supported_language_pairs && service.supported_language_pairs.length > 0) {
      return service.supported_language_pairs.map(pair => ({
        sourceLanguage: pair.sourceLanguage,
        targetLanguage: pair.targetLanguage,
        sourceScriptCode: pair.sourceScriptCode,
        targetScriptCode: pair.targetScriptCode,
      }));
    }
    
    // Otherwise, get from model
    return getSupportedLanguagePairs(service.model_id);
  } catch (error) {
    console.error('Failed to fetch supported language pairs for service:', error);
    throw new Error('Failed to fetch supported language pairs for service');
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
 * Get service by language pair
 * @param languagePair - Source and target language pair
 * @returns Promise with matching service
 */
export const getServiceByLanguagePair = async (
  languagePair: LanguagePair
): Promise<NMTServiceDetailsResponse | null> => {
  try {
    const services = await listNMTServices();
    
    const matchingService = services.find(service =>
      service.supported_languages.includes(languagePair.sourceLanguage) &&
      service.supported_languages.includes(languagePair.targetLanguage)
    );
    
    return matchingService || null;
  } catch (error) {
    console.error('Failed to find service for language pair:', error);
    throw new Error('Failed to find service for language pair');
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
