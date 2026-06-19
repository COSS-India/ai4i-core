// LLM service API client with typed methods

import { LLM_SUPPORTED_LANGUAGES } from '../config/constants';
import { apiService, apiEndpoints } from './api';
import { chatCompletionResponseSchema } from './dto/schemas/inference';
import { LLMInferenceRequest, LLMInferenceResponse } from '../types/llm';
/** Hardcoded model for POST /api/v1/chat/completions (OpenAI-compatible proxy). */
export const LLM_CHAT_MODEL = 'google/gemma-4-E4B-it';
export const AGRINET_MODEL = 'agrinet-model';

export const LLM_CHAT_MODELS = [LLM_CHAT_MODEL, AGRINET_MODEL] as const;

export const isLlmChatService = (id?: string): boolean =>
  (LLM_CHAT_MODELS as readonly string[]).includes(id ?? '');

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

/** Options shown in the LLM Service dropdown. */
export const DEFAULT_LLM_SERVICES: LLMServiceDetailsResponse[] = [
  {
    service_id: LLM_CHAT_MODEL,
    model_id: LLM_CHAT_MODEL,
    model_version: '',
    name: LLM_CHAT_MODEL,
    serviceDescription:
      'Google Gemma 4 instruction-tuned model for contextual translation.',
    endpoint: apiEndpoints.llm.chat,
    supported_languages: LLM_SUPPORTED_LANGUAGES.map((l) => l.code),
  },
  {
    service_id: AGRINET_MODEL,
    model_id: AGRINET_MODEL,
    model_version: '',
    name: AGRINET_MODEL,
    serviceDescription: 'AgriNet model for contextual translation.',
    endpoint: apiEndpoints.llm.chat,
    supported_languages: LLM_SUPPORTED_LANGUAGES.map((l) => l.code),
  },
];

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
 * LLM services for the UI dropdown (fixed chat model; no model-management fetch).
 */
export const listLLMServices = async (): Promise<LLMServiceDetailsResponse[]> =>
  DEFAULT_LLM_SERVICES;

/**
 * Translate via POST /api/v1/chat/completions (OpenAI-compatible). Does not use /llm/inference.
 */
export const performLLMChat = async (
  text: string,
  config: LLMInferenceRequest['config']
): Promise<{ data: LLMInferenceResponse; responseTime: number }> => {
  try {
    const model = config.serviceId ?? LLM_CHAT_MODEL;
    const inputLanguage = config.inputLanguage ?? '';
    const outputLanguage = config.outputLanguage ?? '';
    const content = buildTranslationPrompt(text, inputLanguage, outputLanguage);

    const isAgrinet = model === AGRINET_MODEL;
    const payload = isAgrinet
      ? {
          model: AGRINET_MODEL,
          messages: [{ role: 'user', content }],
          max_tokens: 200,
          chat_template_kwargs: { enable_thinking: false },
        }
      : {
          model: LLM_CHAT_MODEL,
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
