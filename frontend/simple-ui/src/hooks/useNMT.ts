// Custom React hook for NMT functionality with text translation

import { useState, useCallback, useRef } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useToast } from '@chakra-ui/react';
import { performNMTInference } from '../services/nmtService';
import { getWordCount } from '../utils/helpers';
import { UseNMTReturn, NMTInferenceRequest, NMTInferenceResponse, LanguagePair } from '../types/nmt';
import { DEFAULT_NMT_CONFIG, MAX_TEXT_LENGTH, MIN_NMT_TEXT_LENGTH, NMT_ERRORS } from '../config/constants';
import { extractErrorInfo } from '../utils/errorHandler';

// Allow letters (including Unicode/Indic), numbers, spaces, and common punctuation (ES5-compatible: no \p{} or u flag)
const VALID_NMT_CHAR_REGEX = /^[\s.,!?;:'"\-–—()\[\]{}@#$%&*+=\/\\<>~`a-zA-Z0-9\u0900-\u097F\u0980-\u09FF\u0A00-\u0A7F\u0A80-\u0AFF\u0B00-\u0B7F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u0D80-\u0DFF]*$/;

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

  // Only show "text exceeds limit" toast once per exceed (not every keystroke)
  const hasShownTextLimitToastRef = useRef(false);

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
        const nmtErr = NMT_ERRORS.TRANSLATION_FAILED;
        setError(nmtErr.description);
        setFetching(false);
        toast({
          title: nmtErr.title,
          description: nmtErr.description,
          status: 'error',
          duration: 5000,
          isClosable: true,
        });
      }
    },
    onError: (error: any) => {
      console.error('NMT inference error:', error);
      
      // Use centralized error handler (NMT context so backend message shown as default when no specific mapping)
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error, 'nmt');
      
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
    const trimmed = text?.trim() ?? '';
    
    if (!text) {
      const err = NMT_ERRORS.NO_TEXT_INPUT;
      toast({
        title: err.title,
        description: err.description,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    
    if (trimmed === '') {
      const err = NMT_ERRORS.EMPTY_INPUT;
      toast({
        title: err.title,
        description: err.description,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    if (trimmed.length < MIN_NMT_TEXT_LENGTH) {
      const err = NMT_ERRORS.TEXT_TOO_SHORT;
      toast({
        title: err.title,
        description: err.description,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    if (text.length > MAX_TEXT_LENGTH) {
      const err = NMT_ERRORS.TEXT_TOO_LONG;
      toast({
        title: err.title,
        description: err.description,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    if (!VALID_NMT_CHAR_REGEX.test(trimmed)) {
      const err = NMT_ERRORS.INVALID_CHARACTERS;
      toast({
        title: err.title,
        description: err.description,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    if (languagePair.sourceLanguage === languagePair.targetLanguage) {
      const err = NMT_ERRORS.SAME_LANGUAGE_ERROR;
      toast({
        title: err.title,
        description: err.description,
        status: 'error',
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

  // Set input text with validation — show toast only when first exceeding limit, not every keystroke
  const setInputTextWithValidation = useCallback((text: string) => {
    setInputText(text);

    if (text.length > MAX_TEXT_LENGTH) {
      if (!hasShownTextLimitToastRef.current) {
        hasShownTextLimitToastRef.current = true;
        const err = NMT_ERRORS.TEXT_TOO_LONG;
        toast({
          id: 'nmt-text-exceeds-limit',
          title: err.title,
          description: err.description,
          status: 'warning',
          duration: 3000,
          isClosable: true,
        });
      }
    } else {
      hasShownTextLimitToastRef.current = false;
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
