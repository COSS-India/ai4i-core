// LLM service API client with typed methods

import { LLM_SUPPORTED_LANGUAGES } from '../config/constants';
import { apiService, apiEndpoints } from './api';
import { chatCompletionResponseSchema } from './dto/schemas/inference';
import { LLMInferenceRequest, LLMInferenceResponse } from '../types/llm';
import { listServices } from './modelManagementService';

/** Model name that needs agrinet-specific chat/completions fields. */
export const AGRINET_MODEL = 'agrinet-model';

export const LLM_CHAT_DEFAULT_SOURCE_LANGUAGE = 'en';
export const LLM_CHAT_DEFAULT_TARGET_LANGUAGE = 'hi';

export interface LLMServiceDetailsResponse {
  service_id: string;
  model_id: string;
  model_version: string;
  name: string;
  serviceDescription: string;
  endpoint: string;
  supported_languages: string[];
}

const getLanguageLabel = (code: string): string => {
  const lang = LLM_SUPPORTED_LANGUAGES.find((l) => l.code === code);
  return lang?.label ?? code;
};

const buildTranslationPrompt = (
  text: string,
  inputLanguage: string,
  outputLanguage: string
): string => {
  const source = getLanguageLabel(inputLanguage);
  const target = getLanguageLabel(outputLanguage);
  return `Translate from ${source} to ${target}. Output only the translation. Text: ${text}`;
};

/**
 * List all available LLM services from
 * GET /api/v1/services?task_type=llm&is_published=true
 */
export const listLLMServices = async (): Promise<LLMServiceDetailsResponse[]> => {
  try {
    const services = await listServices('llm', true);

    const transformed = services.map((service) => {
      const supportedLanguages: string[] = [];
      if (Array.isArray(service.languages)) {
        service.languages.forEach((lang: unknown) => {
          if (typeof lang === 'string') {
            supportedLanguages.push(lang);
          } else if (lang && typeof lang === 'object') {
            const langObj = lang as {
              code?: string;
              language?: string;
              sourceLanguage?: string;
              targetLanguage?: string;
            };
            const langCode =
              langObj.code ||
              langObj.language ||
              langObj.sourceLanguage ||
              langObj.targetLanguage;
            if (langCode) supportedLanguages.push(langCode);
          }
        });
      }

      let endpoint = service.endpoint || '';
      if (endpoint) {
        endpoint = endpoint.replace(/^https?:\/\//, '');
      }

      const serviceId = service.serviceId || service.service_id || '';

      return {
        service_id: serviceId,
        model_id: service.modelId || service.model_id || '',
        model_version: service.modelVersion || service.model_version || '',
        name: service.name || serviceId,
        serviceDescription:
          service.serviceDescription ||
          service.description ||
          'No description available',
        endpoint,
        supported_languages:
          supportedLanguages.length > 0
            ? Array.from(new Set(supportedLanguages))
            : LLM_SUPPORTED_LANGUAGES.map((l) => l.code),
      };
    });

    return transformed.filter(
      (service, index, self) =>
        service.service_id &&
        self.findIndex((s) => s.service_id === service.service_id) === index
    );
  } catch (error) {
    console.error('Failed to fetch LLM services:', error);
    throw new Error('Failed to fetch LLM services');
  }
};

/**
 * Translate via POST /api/v1/chat/completions (OpenAI-compatible).
 * Sends the registry `serviceId` (not the model name).
 */
export const performLLMChat = async (
  text: string,
  config: LLMInferenceRequest['config']
): Promise<{ data: LLMInferenceResponse; responseTime: number }> => {
  try {
    const serviceId = config.serviceId?.trim();
    if (!serviceId) {
      throw new Error('Please select an LLM service.');
    }

    const inputLanguage = config.inputLanguage ?? '';
    const outputLanguage = config.outputLanguage ?? '';
    const content = buildTranslationPrompt(text, inputLanguage, outputLanguage);

    const isAgrinet = config.modelName === AGRINET_MODEL;
    const payload = isAgrinet
      ? {
          serviceId,
          messages: [{ role: 'user', content }],
          max_tokens: 200,
          chat_template_kwargs: { enable_thinking: false },
        }
      : {
          serviceId,
          messages: [{ role: 'user', content }],
          stream: false,
        };

    const response = await apiService.post(
      apiEndpoints.llm.chat,
      payload,
      { responseSchema: chatCompletionResponseSchema, suppressErrorAlert: true }
    );

    const responseTime = Number.parseInt(response.headers['request-duration'] || '0', 10);
    const translated =
      response.data.choices?.[0]?.message?.content?.trim() ?? '';

    const data: LLMInferenceResponse = {
      output: [{ source: text, target: translated }],
    };

    return { data, responseTime };
  } catch (error) {
    console.error('LLM chat error:', error);
    throw error;
  }
};
