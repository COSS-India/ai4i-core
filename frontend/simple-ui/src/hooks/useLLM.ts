// Custom React hook for LLM functionality with text processing

import { useState, useCallback, useEffect, useRef } from 'react';
import { useMutation } from '@tanstack/react-query';
import { showToast } from '../utils/toast';
import {
  performLLMChat,
  LLM_CHAT_DEFAULT_SOURCE_LANGUAGE,
  LLM_CHAT_DEFAULT_TARGET_LANGUAGE,
} from '../services/llmService';
import { getWordCount } from '../utils/helpers';
import { UseLLMReturn, LLMInferenceRequest } from '../types/llm';
import type { InferenceModelMetadata } from '../types/feedback';
import { parseError, showError } from '../utils/errorHandler';

const MAX_TEXT_LENGTH = 50000;

/**
 * @param serviceId - Registry `serviceId` sent as the completions `serviceId` field.
 * @param modelName - Service `name`, used only for model-specific payload handling.
 */
export const useLLM = (serviceId?: string, modelName?: string): UseLLMReturn => {
  const [selectedModelId, setSelectedModelId] = useState<string>('');
  const [inputLanguage, setInputLanguage] = useState<string>(
    LLM_CHAT_DEFAULT_SOURCE_LANGUAGE
  );
  const [outputLanguage, setOutputLanguage] = useState<string>(
    LLM_CHAT_DEFAULT_TARGET_LANGUAGE
  );
  const [inputText, setInputText] = useState<string>('');
  const [outputText, setOutputText] = useState<string>('');
  const [fetching, setFetching] = useState<boolean>(false);
  const [fetched, setFetched] = useState<boolean>(false);
  const [requestWordCount, setRequestWordCount] = useState<number>(0);
  const [responseWordCount, setResponseWordCount] = useState<number>(0);
  const [requestTime, setRequestTime] = useState<string>('0');
  const [error, setError] = useState<string | null>(null);
  const [lastRequestId, setLastRequestId] = useState<string | null>(null);
  const [lastModelMeta, setLastModelMeta] = useState<InferenceModelMetadata | null>(null);

  const hasShownTextLimitToastRef = useRef(false);

  useEffect(() => {
    if (!modelName) return;
    setInputLanguage(LLM_CHAT_DEFAULT_SOURCE_LANGUAGE);
    setOutputLanguage(LLM_CHAT_DEFAULT_TARGET_LANGUAGE);
  }, [modelName]);

  const llmMutation = useMutation({
    mutationFn: async (text: string) => {
      const config: LLMInferenceRequest['config'] = {
        serviceId: serviceId || selectedModelId,
        modelName,
        inputLanguage,
        outputLanguage,
      };
      return performLLMChat(text, config);
    },
    onSuccess: (response) => {
      try {
        const output = response.data.output[0]?.target || '';
        setOutputText(output);
        setResponseWordCount(getWordCount(output));
        setRequestTime(response.responseTime.toString());
        setLastRequestId(response.requestId ?? null);
        setLastModelMeta(response.model ?? response.data.model ?? null);
        setFetched(true);
        setFetching(false);
        setError(null);
      } catch (err) {
        console.error('Error processing LLM response:', err);
        setError('Failed to process LLM response.');
        setFetching(false);
      }
    },
    onError: (error: unknown) => {
      console.error('LLM chat error:', error);
      const { message: errorMessage } = parseError(error);
      setError(errorMessage);
      setFetching(false);
      showError(error);
    },
  });

  const performInference = useCallback(
    async (text: string) => {
      if (!text || text.trim() === '') {
        showToast({ type: 'warning', message: 'Please enter text to process.' });
        return;
      }

      if (text.length > MAX_TEXT_LENGTH) {
        showToast({
          type: 'warning',
          message: `Text length exceeds maximum limit of ${MAX_TEXT_LENGTH} characters.`,
        });
        return;
      }

      const effectiveModel = serviceId || selectedModelId;
      if (!effectiveModel) {
        showToast({ type: 'warning', message: 'Please select an LLM service.' });
        return;
      }

      if (!inputLanguage?.trim() || !outputLanguage?.trim()) {
        showToast({
          type: 'warning',
          message: 'Please select both source and target languages.',
        });
        return;
      }

      try {
        setFetching(true);
        setError(null);
        setRequestWordCount(getWordCount(text));
        await llmMutation.mutateAsync(text);
      } catch (err) {
        console.error('LLM chat error:', err);
      }
    },
    [
      llmMutation,
      serviceId,
      selectedModelId,
      inputLanguage,
      outputLanguage,
    ]
  );

  const setInputTextWithValidation = useCallback(
    (text: string) => {
      setInputText(text);

      if (text.length > MAX_TEXT_LENGTH) {
        if (!hasShownTextLimitToastRef.current) {
          hasShownTextLimitToastRef.current = true;
          showToast({
            type: 'warning',
            message: `Text length (${text.length}) exceeds recommended limit of ${MAX_TEXT_LENGTH} characters.`,
          });
        }
      } else {
        hasShownTextLimitToastRef.current = false;
      }
    },
    []
  );

  const clearResults = useCallback(() => {
    setOutputText('');
    setFetched(false);
    setLastRequestId(null);
    setLastModelMeta(null);
    setFetching(false);
    setRequestWordCount(0);
    setResponseWordCount(0);
    setRequestTime('0');
    setError(null);
  }, []);

  const swapLanguages = useCallback(() => {
    const tempLang = inputLanguage;
    setInputLanguage(outputLanguage);
    setOutputLanguage(tempLang);

    const tempText = inputText;
    setInputText(outputText);
    setOutputText(tempText);
  }, [inputLanguage, outputLanguage, inputText, outputText]);

  return {
    selectedModelId,
    inputLanguage,
    outputLanguage,
    inputText,
    outputText,
    fetching,
    fetched,
    requestWordCount,
    responseWordCount,
    requestTime,
    error,
    lastRequestId,
    lastModelMeta,
    performInference,
    setInputText: setInputTextWithValidation,
    setInputLanguage,
    setOutputLanguage,
    setSelectedModelId,
    clearResults,
    swapLanguages,
  };
};
