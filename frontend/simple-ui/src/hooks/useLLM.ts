// Custom React hook for LLM functionality with text processing

import { useState, useCallback, useEffect, useRef } from 'react';
import { useMutation } from '@tanstack/react-query';
import { showToast } from '../utils/toast';
import {
  performLLMChat,
  isLlmChatService,
  LLM_CHAT_DEFAULT_SOURCE_LANGUAGE,
  LLM_CHAT_DEFAULT_TARGET_LANGUAGE,
} from '../services/llmService';
import { getWordCount } from '../utils/helpers';
import { UseLLMReturn, LLMInferenceRequest } from '../types/llm';
import { parseError, showError } from '../utils/errorHandler';

const MAX_TEXT_LENGTH = 50000;

export const useLLM = (serviceId?: string): UseLLMReturn => {
  const useChatDefaults = isLlmChatService(serviceId);

  const [selectedModelId, setSelectedModelId] = useState<string>('');
  const [inputLanguage, setInputLanguage] = useState<string>(
    useChatDefaults ? LLM_CHAT_DEFAULT_SOURCE_LANGUAGE : ''
  );
  const [outputLanguage, setOutputLanguage] = useState<string>(
    useChatDefaults ? LLM_CHAT_DEFAULT_TARGET_LANGUAGE : ''
  );
  const [inputText, setInputText] = useState<string>('');
  const [outputText, setOutputText] = useState<string>('');
  const [fetching, setFetching] = useState<boolean>(false);
  const [fetched, setFetched] = useState<boolean>(false);
  const [requestWordCount, setRequestWordCount] = useState<number>(0);
  const [responseWordCount, setResponseWordCount] = useState<number>(0);
  const [requestTime, setRequestTime] = useState<string>('0');
  const [error, setError] = useState<string | null>(null);

  const hasShownTextLimitToastRef = useRef(false);

  useEffect(() => {
    if (!isLlmChatService(serviceId)) return;
    setInputLanguage(LLM_CHAT_DEFAULT_SOURCE_LANGUAGE);
    setOutputLanguage(LLM_CHAT_DEFAULT_TARGET_LANGUAGE);
  }, [serviceId]);

  const llmMutation = useMutation({
    mutationFn: async (text: string) => {
      const config: LLMInferenceRequest['config'] = {
        serviceId: serviceId || selectedModelId,
        inputLanguage,
        outputLanguage,
      };
      return performLLMChat(text, config);
    },
    onSuccess: (response: { data: { output: { target?: string }[] }; responseTime: number }) => {
      try {
        const output = response.data.output[0]?.target || '';
        setOutputText(output);
        setResponseWordCount(getWordCount(output));
        setRequestTime(response.responseTime.toString());
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

      const effectiveServiceId = serviceId || selectedModelId;
      if (!effectiveServiceId) {
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
    performInference,
    setInputText: setInputTextWithValidation,
    setInputLanguage,
    setOutputLanguage,
    setSelectedModelId,
    clearResults,
    swapLanguages,
  };
};
