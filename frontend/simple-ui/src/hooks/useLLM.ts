// Custom React hook for LLM functionality with text processing

import { useState, useCallback } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useToast } from '@chakra-ui/react';
import { performLLMInference } from '../services/llmService';
import { performNMTInference } from '../services/nmtService';
import { getWordCount } from '../utils/helpers';
import { UseLLMReturn, LLMInferenceRequest } from '../types/llm';

const MAX_TEXT_LENGTH = 50000;
const DEFAULT_LLM_CONFIG = {
  serviceId: 'llm',
  inputLanguage: 'en',
  outputLanguage: 'hi',
};

export const useLLM = (): UseLLMReturn => {
  // State
  const [selectedModelId, setSelectedModelId] = useState<string>('llm');
  const [inputLanguage, setInputLanguage] = useState<string>('en');
  const [outputLanguage, setOutputLanguage] = useState<string>('hi');
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

  // Toast hook
  const toast = useToast();

  // LLM inference mutation
  const llmMutation = useMutation({
    mutationFn: async (text: string) => {
      const config: LLMInferenceRequest['config'] = {
        serviceId: selectedModelId,
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
      
      // Check for 401 authentication errors
      let errorMessage = 'Failed to process text. Please try again.';
      let errorTitle = 'Processing Error';
      
      if (error?.response?.status === 401 || error?.status === 401 || error?.message?.includes('401')) {
        errorTitle = 'Authentication Failed';
        // Check if it's an API key issue
        if (error?.message?.includes('API key') || error?.message?.includes('api key')) {
          errorMessage = 'API key is missing or invalid. Please set a valid API key in your profile.';
        } else if (error?.message?.includes('token') || error?.message?.includes('Token')) {
          errorMessage = 'Your session has expired. Please sign in again.';
        } else {
          errorMessage = 'Authentication failed. Please check your API key and login status, then try again.';
        }
      } else if (error?.message) {
        errorMessage = error.message;
      }
      
      setError(errorMessage);
      setFetching(false);
      toast({
        title: errorTitle,
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
  }, [llmMutation, toast]);

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

    try {
      setIsDualMode(true);
      setFetching(true);
      setError(null);
      setRequestWordCount(getWordCount(text));
      
      // Call both LLM and NMT in parallel
      const [llmResponse, nmtResponse] = await Promise.all([
        performLLMInference(text, {
          serviceId: selectedModelId,
          inputLanguage: inputLanguage,
          outputLanguage: outputLanguage,
        }),
        performNMTInference(text, {
          language: {
            sourceLanguage: inputLanguage,
            targetLanguage: outputLanguage,
          },
          serviceId: 'nmt',
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
  }, [selectedModelId, inputLanguage, outputLanguage, toast]);

  // Set input text with validation
  const setInputTextWithValidation = useCallback((text: string) => {
    setInputText(text);
    
    if (text.length > MAX_TEXT_LENGTH) {
      toast({
        title: 'Text Length Warning',
        description: `Text length (${text.length}) exceeds recommended limit of ${MAX_TEXT_LENGTH} characters.`,
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
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

