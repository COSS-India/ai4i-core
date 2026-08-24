// LLM service API client with typed methods

import { LLM_SUPPORTED_LANGUAGES, UI_ERROR_MESSAGES } from '../config/constants';
import { apiService, apiEndpoints } from './api';
import { chatCompletionResponseSchema } from './dto/schemas/inference';
import { LLMInferenceRequest, LLMInferenceResponse } from '../types/llm';
import { listServices } from './modelManagementService';
import {
  listTryItServices,
  pickLowestServiceId,
  selectTryItDefaultService,
  trackTryItRequest,
} from './tryItService';
import { getAnonymousSessionId, isAnonymousUser } from '../utils/anonymousSession';

/** Model name that needs agrinet-specific chat/completions fields. */
export const AGRINET_MODEL = 'agrinet-model';

export const LLM_CHAT_DEFAULT_SOURCE_LANGUAGE = 'en';
export const LLM_CHAT_DEFAULT_TARGET_LANGUAGE = '';

export interface LLMServiceDetailsResponse {
  service_id: string;
  model_id: string;
  model_version: string;
  name: string;
  serviceDescription: string;
  endpoint: string;
  /** Languages that appeared as a sourceLanguage (or an undirected code/language/string entry). */
  supported_source_languages: string[];
  /** Languages that appeared as a targetLanguage (or an undirected code/language/string entry). */
  supported_target_languages: string[];
  /** Directed source→target pairs from entries that had both fields set — lets the UI restrict one side by the other's selection. */
  language_pairs: Array<{ source: string; target: string }>;
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

const getTryItHeaders = () => ({
  'X-Anonymous-Session-Id': getAnonymousSessionId(),
  'X-Try-It': 'true',
});

function mapServiceToLLMDetails(service: Record<string, any>): LLMServiceDetailsResponse {
  // Split strictly by direction: a code only counts as a target option if it
  // actually appeared in a targetLanguage field (never inferred from source).
  const sourceLanguages: string[] = [];
  const targetLanguages: string[] = [];
  const languagePairs: Array<{ source: string; target: string }> = [];
  if (Array.isArray(service.languages)) {
    service.languages.forEach((lang: unknown) => {
      if (typeof lang === 'string') {
        // No direction info on a plain string entry — offer it on both sides.
        sourceLanguages.push(lang);
        targetLanguages.push(lang);
      } else if (lang && typeof lang === 'object') {
        const langObj = lang as {
          code?: string;
          language?: string;
          sourceLanguage?: string;
          targetLanguage?: string;
        };
        const undirected = langObj.code || langObj.language;
        if (undirected) {
          sourceLanguages.push(undirected);
          targetLanguages.push(undirected);
        }
        if (langObj.sourceLanguage) sourceLanguages.push(langObj.sourceLanguage);
        if (langObj.targetLanguage) targetLanguages.push(langObj.targetLanguage);
        // A directed pair only exists when both sides are set on the same entry.
        if (langObj.sourceLanguage && langObj.targetLanguage) {
          languagePairs.push({
            source: langObj.sourceLanguage,
            target: langObj.targetLanguage,
          });
        }
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
    // No fallback to the full language list: a service with no configured
    // languages on a given side should present no selectable languages there.
    supported_source_languages: Array.from(new Set(sourceLanguages)),
    supported_target_languages: Array.from(new Set(targetLanguages)),
    language_pairs: dedupePairs(languagePairs),
  };
}

function dedupePairs(
  pairs: Array<{ source: string; target: string }>
): Array<{ source: string; target: string }> {
  const seen = new Set<string>();
  return pairs.filter((pair) => {
    const key = `${pair.source}\0${pair.target}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function dedupeByServiceId(
  services: LLMServiceDetailsResponse[]
): LLMServiceDetailsResponse[] {
  return services.filter(
    (service, index, self) =>
      service.service_id &&
      self.findIndex((s) => s.service_id === service.service_id) === index
  );
}

function buildChatPayload(
  serviceId: string,
  content: string,
  modelName?: string
): Record<string, unknown> {
  const isAgrinet = modelName === AGRINET_MODEL;
  if (isAgrinet) {
    return {
      model: serviceId,
      messages: [{ role: 'user', content }],
      max_tokens: 200,
      chat_template_kwargs: { enable_thinking: false },
    };
  }
  return {
    model: serviceId,
    messages: [{ role: 'user', content }],
    stream: false,
  };
}

function parseChatCompletionResponse(
  responseData: { choices?: Array<{ message?: { content?: string } }> },
  sourceText: string,
  responseTime: number
): { data: LLMInferenceResponse; responseTime: number } {
  const translated = responseData.choices?.[0]?.message?.content?.trim() ?? '';
  return {
    data: { output: [{ source: sourceText, target: translated }] },
    responseTime,
  };
}

/**
 * Anonymous try-it list — one service.
 * Prefer `isTryItDefault`; else lowest service_id (previous deterministic pick).
 * GET /services/try-it-service-list?task_types=llm
 */
async function listAnonymousLLMServices(): Promise<LLMServiceDetailsResponse[]> {
  try {
    const raw = await listTryItServices('llm');
    const selected = selectTryItDefaultService(raw, pickLowestServiceId);
    return dedupeByServiceId(selected.map((s) => mapServiceToLLMDetails(s)));
  } catch (error) {
    console.error('Failed to fetch try-it LLM services:', error);
    throw new Error('Failed to fetch LLM services for try-it');
  }
}

async function listAuthenticatedLLMServices(): Promise<LLMServiceDetailsResponse[]> {
  try {
    const services = await listServices('llm', true);
    return dedupeByServiceId(services.map((s) => mapServiceToLLMDetails(s)));
  } catch (error) {
    console.error('Failed to fetch LLM services:', error);
    throw new Error('Failed to fetch LLM services');
  }
}

/**
 * List available LLM services from the registry.
 * Anonymous: try-it service list.
 * Authenticated: published LLM services.
 */
export const listLLMServices = async (): Promise<LLMServiceDetailsResponse[]> => {
  if (isAnonymousUser()) {
    return listAnonymousLLMServices();
  }
  return listAuthenticatedLLMServices();
};

/**
 * Anonymous LLM try-it via POST /api/v1/llm/try-it (OpenAI-compatible body).
 */
export const performTryItLLMChat = async (
  text: string,
  config: LLMInferenceRequest['config']
): Promise<{ data: LLMInferenceResponse; responseTime: number }> => {
  const serviceId = config.serviceId?.trim();
  if (!serviceId) {
    throw new Error('Please select an LLM service.');
  }

  const content = buildTranslationPrompt(
    text,
    config.inputLanguage ?? '',
    config.outputLanguage ?? ''
  );
  const modelName =
    typeof config.modelName === 'string' ? config.modelName : undefined;
  const payload = buildChatPayload(serviceId, content, modelName);

  try {
    const response = await apiService.post(
      apiEndpoints.llm.tryIt,
      payload,
      {
        headers: getTryItHeaders(),
        responseSchema: chatCompletionResponseSchema,
        suppressErrorAlert: true,
      }
    );

    trackTryItRequest();

    const responseTime = Number.parseInt(response.headers['request-duration'] || '0', 10);
    return parseChatCompletionResponse(response.data, text, responseTime);
  } catch (error: any) {
    console.error('Try-It LLM chat error:', error);

    if (error?.response?.status === 403 || error?.response?.status === 429) {
      const rawMessage: string =
        (typeof error?.response?.data?.detail === 'string' ? error?.response?.data?.detail : '') ||
        error?.response?.data?.detail?.message ||
        error?.response?.data?.error_msg ||
        error?.response?.data?.message ||
        '';

      if (
        rawMessage.toLowerCase().includes('login') ||
        rawMessage.toLowerCase().includes('rate') ||
        error?.response?.status === 429
      ) {
        throw new Error(UI_ERROR_MESSAGES.TRY_IT_RATE_LIMIT);
      }

      throw new Error(UI_ERROR_MESSAGES.TRY_IT_LOGIN_REQUIRED);
    }

    if (error?.message) {
      throw error;
    }
    throw new Error(UI_ERROR_MESSAGES.TRY_IT_TRANSLATION_FAILED);
  }
};

/**
 * Translate via chat completions.
 * Anonymous → POST /api/v1/llm/try-it
 * Authenticated → POST /api/v1/chat/completions
 */
export const performLLMChat = async (
  text: string,
  config: LLMInferenceRequest['config']
): Promise<{ data: LLMInferenceResponse; responseTime: number }> => {
  if (isAnonymousUser()) {
    return performTryItLLMChat(text, config);
  }

  try {
    const serviceId = config.serviceId?.trim();
    if (!serviceId) {
      throw new Error('Please select an LLM service.');
    }

    const content = buildTranslationPrompt(
      text,
      config.inputLanguage ?? '',
      config.outputLanguage ?? ''
    );
    const modelName =
    typeof config.modelName === 'string' ? config.modelName : undefined;
  const payload = buildChatPayload(serviceId, content, modelName);

    const response = await apiService.post(
      apiEndpoints.llm.chat,
      payload,
      { responseSchema: chatCompletionResponseSchema, suppressErrorAlert: true }
    );

    const responseTime = Number.parseInt(response.headers['request-duration'] || '0', 10);
    return parseChatCompletionResponse(response.data, text, responseTime);
  } catch (error) {
    console.error('LLM chat error:', error);
    throw error;
  }
};
