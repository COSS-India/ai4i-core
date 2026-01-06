// Custom React hook for NMT functionality with text translation

import { useState, useCallback } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useToast } from '@chakra-ui/react';
import { performNMTInference } from '../services/nmtService';
import { getWordCount } from '../utils/helpers';
import { UseNMTReturn, NMTInferenceRequest, NMTInferenceResponse, LanguagePair } from '../types/nmt';
import { DEFAULT_NMT_CONFIG, MAX_TEXT_LENGTH } from '../config/constants';

export const useNMT = (): UseNMTReturn => {
  // State
  const [languagePair, setLanguagePair] = useState<LanguagePair>(DEFAULT_NMT_CONFIG);
  const [selectedServiceId, setSelectedServiceId] = useState<string>('');
  const [inputText, setInputText] = useState<string>('');
  const [translatedText, setTranslatedText] = useState<string>('');
  const [fetching, setFetching] = useState<boolean>(false);
  const [fetched, setFetched] = useState<boolean>(false);
  const [requestWordCount, setRequestWordCount] = useState<number>(0);
  const [responseWordCount, setResponseWordCount] = useState<number>(0);
  const [requestTime, setRequestTime] = useState<string>('0');
  const [error, setError] = useState<string | null>(null);

  // Toast hook
  const toast = useToast();

  // NMT inference mutation
  const nmtMutation = useMutation({
    mutationFn: async (text: string) => {
      const config: NMTInferenceRequest['config'] = {
        language: {
          sourceLanguage: languagePair.sourceLanguage,
          targetLanguage: languagePair.targetLanguage,
          sourceScriptCode: languagePair.sourceScriptCode,
          targetScriptCode: languagePair.targetScriptCode,
        },
        serviceId: selectedServiceId,
      };

      return performNMTInference(text, config);
    },
    onSuccess: (response: { data: NMTInferenceResponse; responseTime: number }) => {
      try {
        const translation = response.data.output[0]?.target || '';
        setTranslatedText(translation);
        setResponseWordCount(getWordCount(translation));
        
        // Update request time with actual API response time (in milliseconds)
        setRequestTime(response.responseTime.toString());
        
        setFetched(true);
        setFetching(false);
        setError(null);
      } catch (err) {
        console.error('Error processing NMT response:', err);
        setError('Failed to process translation response.');
        setFetching(false);
      }
    },
    onError: (error: any) => {
      console.error('NMT inference error:', error);
      
      // Prioritize API error message from response
      let errorMessage = 'Failed to translate text. Please try again.';
      let errorTitle = 'Translation Error';
      
      // Check for API error message first (from detail.message or detail.error)
      if (error?.response?.data?.detail?.message) {
        errorMessage = error.response.data.detail.message;
        // Use error code for title if available
        if (error.response.data.detail.error) {
          errorTitle = error.response.data.detail.error;
        } else if (error.response.data.detail.code) {
          errorTitle = error.response.data.detail.code;
        }
      } else if (error?.response?.data?.message) {
        errorMessage = error.response.data.message;
      } else if (error?.response?.data?.detail) {
        // Handle case where detail is a string
        if (typeof error.response.data.detail === 'string') {
          errorMessage = error.response.data.detail;
        }
      } else if (error?.response?.status === 401 || error?.status === 401 || error?.message?.includes('401')) {
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
        description: 'Please enter text to translate.',
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

    if (languagePair.sourceLanguage === languagePair.targetLanguage) {
      toast({
        title: 'Invalid Language Pair',
        description: 'Source and target languages must be different.',
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    // Require a model/service to be selected before translating
    if (!selectedServiceId) {
      toast({
        title: 'Select a model',
        description: 'Please select a translation model before testing.',
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    try {
      setFetching(true);
      setError(null);
      setRequestWordCount(getWordCount(text));
      await nmtMutation.mutateAsync(text);
    } catch (err) {
      console.error('Inference error:', err);
    }
  }, [nmtMutation, languagePair, toast, selectedServiceId]);

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

  // Set language pair
  const setLanguagePairWithValidation = useCallback((pair: LanguagePair) => {
    setLanguagePair(pair);
    setInputText('');
    setTranslatedText('');
    setFetched(false);
    setError(null);
  }, []);

  // Clear results
  const clearResults = useCallback(() => {
    setTranslatedText('');
    setFetched(false);
    setFetching(false);
    setRequestWordCount(0);
    setResponseWordCount(0);
    setRequestTime('0');
    setError(null);
  }, []);

  // Swap languages
  const swapLanguages = useCallback(() => {
    const newPair: LanguagePair = {
      sourceLanguage: languagePair.targetLanguage,
      targetLanguage: languagePair.sourceLanguage,
      sourceScriptCode: languagePair.targetScriptCode,
      targetScriptCode: languagePair.sourceScriptCode,
    };
    
    setLanguagePairWithValidation(newPair);
    
    // Also swap the texts
    const tempText = inputText;
    setInputText(translatedText);
    setTranslatedText(tempText);
  }, [languagePair, inputText, translatedText, setLanguagePairWithValidation]);

  return {
    // State
    languagePair,
    selectedServiceId,
    inputText,
    translatedText,
    fetching,
    fetched,
    requestWordCount,
    responseWordCount,
    requestTime,
    error,
    
    // Methods
    performInference,
    setInputText: setInputTextWithValidation,
    setLanguagePair: setLanguagePairWithValidation,
    setSelectedServiceId,
    clearResults,
    swapLanguages,
  };
};
