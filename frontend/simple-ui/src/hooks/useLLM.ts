// Custom React hook for LLM functionality with text processing

import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useToastWithDeduplication } from './useToastWithDeduplication';
import { performLLMInference } from '../services/llmService';
import { listNMTServices, performNMTInference } from '../services/nmtService';
import { getWordCount } from '../utils/helpers';
import { UseLLMReturn, LLMInferenceRequest } from '../types/llm';
import { extractErrorInfo } from '../utils/errorHandler';
import type { NMTServiceDetailsResponse } from '../types/nmt';

const MAX_TEXT_LENGTH = 50000;

export const useLLM = (serviceId?: string): UseLLMReturn => {
  // State
  const [selectedModelId, setSelectedModelId] = useState<string>('');
  const [inputLanguage, setInputLanguage] = useState<string>('');
  const [outputLanguage, setOutputLanguage] = useState<string>('');
  const [inputText, setInputText] = useState<string>('');
  const [outputText, setOutputText] = useState<string>('');
  const [nmtOutputText, setNmtOutputText] = useState<string>('');
  const [fetching, setFetching] = useState<boolean>(false);
  const [fetched, setFetched] = useState<boolean>(false);
  const [isDualMode, setIsDualMode] = useState<boolean>(false);
  const [requestWordCount, setRequestWordCount] = useState<number>(0);
  const [responseWordCount, setResponseWordCount] = useState<number>(0);
  const [nmtResponseWordCount, setNmtResponseWordCount] = useState<number>(0);
  const [requestTime, setRequestTime] = useState<string>('0');
  const [nmtRequestTime, setNmtRequestTime] = useState<string>('0');
  const [error, setError] = useState<string | null>(null);

  const [nmtServiceId, setNmtServiceId] = useState<string>('');
  const [nmtServiceDetails, setNmtServiceDetails] = useState<NMTServiceDetailsResponse | null>(null);

  // Only show "text exceeds limit" toast once per exceed (not every keystroke)
  const hasShownTextLimitToastRef = useRef(false);

  // Toast hook
  const toast = useToastWithDeduplication();

  const { data: nmtServices } = useQuery({
    queryKey: ['nmt-services-for-llm'],
    queryFn: listNMTServices,
    staleTime: 10 * 60 * 1000, // 10 minutes
  });

  const defaultPublishedNmtService = useMemo(() => {
    if (!nmtServices || nmtServices.length === 0) return null;

    // Logged-in users already get published-only via listNMTServices().
    // For anonymous/try-it responses (or future API changes), prefer an explicitly-published service when present.
    const anyWithPublishedFlag = (nmtServices as any[]).find(
      (s) => s && (s.is_published === true || s.isPublished === true || s.status === 'published')
    ) as NMTServiceDetailsResponse | undefined;

    return anyWithPublishedFlag ?? nmtServices[0];
  }, [nmtServices]);

  useEffect(() => {
    if (!defaultPublishedNmtService) return;
    setNmtServiceId(defaultPublishedNmtService.service_id);
    setNmtServiceDetails(defaultPublishedNmtService);
  }, [defaultPublishedNmtService]);

  // LLM inference mutation
  const llmMutation = useMutation({
    mutationFn: async (text: string) => {
      // Use the provided serviceId if available, otherwise fall back to selectedModelId
      const effectiveServiceId = serviceId || selectedModelId;
      
      const config: LLMInferenceRequest['config'] = {
        serviceId: effectiveServiceId,
        inputLanguage: inputLanguage,
        outputLanguage: outputLanguage,
      };

      return performLLMInference(text, config);
    },
    onSuccess: (response: { data: any; responseTime: number }) => {
      try {
        const output = response.data.output[0]?.target || '';
        setOutputText(output);
        setResponseWordCount(getWordCount(output));
        
        // Update request time with actual API response time (in milliseconds)
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
    onError: (error: any) => {
      console.error('LLM inference error:', error);
      
      // Use centralized error handler
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error);
      
      setError(errorMessage);
      setFetching(false);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMessage,
        status: 'error',
        duration: 7000,
        isClosable: true,
      });
    },
  });

  // Perform inference
  const performInference = useCallback(async (text: string) => {
    if (!text || text.trim() === '') {
      toast({
        title: 'Input Required',
        description: 'Please enter text to process.',
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    if (text.length > MAX_TEXT_LENGTH) {
      toast({
        title: 'Text Too Long',
        description: `Text length exceeds maximum limit of ${MAX_TEXT_LENGTH} characters.`,
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    // Validate that a service is selected
    const effectiveServiceId = serviceId || selectedModelId;
    if (!effectiveServiceId) {
      toast({
        title: 'Service Required',
        description: 'Please select an LLM service.',
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    // Validate that source and target languages are selected
    if (!inputLanguage?.trim() || !outputLanguage?.trim()) {
      toast({
        title: 'Language Required',
        description: 'Please select both source and target languages.',
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    try {
      setIsDualMode(false);
      setFetching(true);
      setError(null);
      setRequestWordCount(getWordCount(text));
      setNmtOutputText('');
      await llmMutation.mutateAsync(text);
    } catch (err) {
      console.error('Inference error:', err);
    }
  }, [llmMutation, toast, serviceId, selectedModelId]);

  // Perform dual inference (LLM + NMT)
  const performDualInference = useCallback(async (text: string) => {
    if (!text || text.trim() === '') {
      toast({
        title: 'Input Required',
        description: 'Please enter text to process.',
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    if (text.length > MAX_TEXT_LENGTH) {
      toast({
        title: 'Text Too Long',
        description: `Text length exceeds maximum limit of ${MAX_TEXT_LENGTH} characters.`,
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    // Validate that a service is selected
    const effectiveServiceId = serviceId || selectedModelId;
    if (!effectiveServiceId) {
      toast({
        title: 'Service Required',
        description: 'Please select an LLM service.',
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    // Validate that source and target languages are selected
    if (!inputLanguage?.trim() || !outputLanguage?.trim()) {
      toast({
        title: 'Language Required',
        description: 'Please select both source and target languages.',
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    if (!nmtServiceId) {
      toast({
        title: 'NMT Service Unavailable',
        description: 'No published NMT service is available right now. Please try again later.',
        status: 'warning',
        duration: 4000,
        isClosable: true,
      });
      return;
    }

    try {
      setIsDualMode(true);
      setFetching(true);
      setError(null);
      setRequestWordCount(getWordCount(text));
      
      // Call both LLM and NMT in parallel
      const [llmResponse, nmtResponse] = await Promise.all([
        performLLMInference(text, {
          serviceId: effectiveServiceId,
          inputLanguage: inputLanguage,
          outputLanguage: outputLanguage,
        }),
        performNMTInference(text, {
          language: {
            sourceLanguage: inputLanguage,
            targetLanguage: outputLanguage,
          },
          serviceId: nmtServiceId,
        }),
      ]);

      // Process LLM response
      const llmOutput = llmResponse.data.output[0]?.target || '';
      setOutputText(llmOutput);
      setResponseWordCount(getWordCount(llmOutput));
      setRequestTime(llmResponse.responseTime.toString());

      // Process NMT response
      const nmtOutput = nmtResponse.data.output[0]?.target || '';
      setNmtOutputText(nmtOutput);
      setNmtResponseWordCount(getWordCount(nmtOutput));
      setNmtRequestTime(nmtResponse.responseTime.toString());

      setFetched(true);
      setFetching(false);
      setError(null);
    } catch (err: any) {
      console.error('Dual inference error:', err);
      setError('Failed to process text. Please try again.');
      setFetching(false);
      toast({
        title: 'Processing Error',
        description: 'Failed to process text. Please check your connection and try again.',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    }
  }, [serviceId, selectedModelId, inputLanguage, outputLanguage, toast, nmtServiceId]);

  // Set input text with validation — show toast only when first exceeding limit, not every keystroke
  const setInputTextWithValidation = useCallback((text: string) => {
    setInputText(text);

    if (text.length > MAX_TEXT_LENGTH) {
      if (!hasShownTextLimitToastRef.current) {
        hasShownTextLimitToastRef.current = true;
        toast({
          id: 'llm-text-exceeds-limit',
          title: 'Text Length Warning',
          description: `Text length (${text.length}) exceeds recommended limit of ${MAX_TEXT_LENGTH} characters.`,
          status: 'warning',
          duration: 3000,
          isClosable: true,
        });
      }
    } else {
      hasShownTextLimitToastRef.current = false;
    }
  }, [toast]);

  // Clear results
  const clearResults = useCallback(() => {
    setOutputText('');
    setNmtOutputText('');
    setFetched(false);
    setFetching(false);
    setIsDualMode(false);
    setRequestWordCount(0);
    setResponseWordCount(0);
    setNmtResponseWordCount(0);
    setRequestTime('0');
    setNmtRequestTime('0');
    setError(null);
  }, []);

  // Swap languages
  const swapLanguages = useCallback(() => {
    const tempLang = inputLanguage;
    setInputLanguage(outputLanguage);
    setOutputLanguage(tempLang);
    
    // Also swap the texts
    const tempText = inputText;
    setInputText(outputText);
    setOutputText(tempText);
  }, [inputLanguage, outputLanguage, inputText, outputText]);

  return {
    // State
    selectedModelId,
    inputLanguage,
    outputLanguage,
    inputText,
    outputText,
    nmtOutputText,
    fetching,
    fetched,
    isDualMode,
    requestWordCount,
    responseWordCount,
    nmtResponseWordCount,
    requestTime,
    nmtRequestTime,
    error,
    
    // Methods
    performInference,
    performDualInference,
    setInputText: setInputTextWithValidation,
    setInputLanguage,
    setOutputLanguage,
    setSelectedModelId,
    clearResults,
    swapLanguages,
  };
};
