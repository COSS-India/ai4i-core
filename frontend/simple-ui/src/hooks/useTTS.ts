// Custom React hook for TTS functionality with text input and audio generation

import { useState, useCallback, useRef } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useToastWithDeduplication } from './useToastWithDeduplication';
import { performTTSInference } from '../services/ttsService';
import { getWordCount } from '../utils/helpers';
import { UseTTSReturn, TTSInferenceRequest, Gender, AudioFormat, SampleRate } from '../types/tts';
import { DEFAULT_TTS_CONFIG, MAX_TEXT_LENGTH, MIN_TTS_TEXT_LENGTH, TTS_ERRORS } from '../config/constants';
import { extractErrorInfo } from '../utils/errorHandler';

// Allow letters (including Unicode/Indic), numbers, spaces, and common punctuation (ES5-compatible: no \p{} or u flag)
const VALID_TTS_CHAR_REGEX = /^[\s.,!?;:'"\-–—()\[\]{}@#$%&*+=\/\\<>~`a-zA-Z0-9\u0900-\u097F\u0980-\u09FF\u0A00-\u0A7F\u0A80-\u0AFF\u0B00-\u0B7F\u0B80-\u0BFF\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F\u0D80-\u0DFF]*$/;

// Helper function to get the correct service ID based on language
const getServiceIdForLanguage = (language: string): string => {
  // Dravidian languages
  if (['kn', 'ml', 'ta', 'te'].includes(language)) {
    return 'indic-tts-coqui-dravidian';
  }
  // Indo-Aryan languages (expanded as requested)
  if (['hi', 'bn', 'gu', 'mr', 'pa', 'as', 'or'].includes(language)) {
    return 'indic-tts-coqui-indo_aryan';
  }
  // Miscellaneous languages (English, etc.)
  return 'indic-tts-coqui-misc';
};

export const useTTS = (serviceId?: string): UseTTSReturn => {
  // State
  const [language, setLanguage] = useState<string>(DEFAULT_TTS_CONFIG.language);
  const [gender, setGender] = useState<Gender>(DEFAULT_TTS_CONFIG.gender);
  const [audioFormat, setAudioFormat] = useState<AudioFormat>(DEFAULT_TTS_CONFIG.audioFormat);
  const [samplingRate, setSamplingRate] = useState<SampleRate>(DEFAULT_TTS_CONFIG.sampleRate);
  const [modelId, setModelId] = useState<string>(getServiceIdForLanguage(DEFAULT_TTS_CONFIG.language));
  const [inputText, setInputText] = useState<string>('');
  const [audio, setAudio] = useState<string>('');
  const [fetching, setFetching] = useState<boolean>(false);
  const [fetched, setFetched] = useState<boolean>(false);
  const [requestWordCount, setRequestWordCount] = useState<number>(0);
  const [requestTime, setRequestTime] = useState<string>('0');
  const [audioDuration, setAudioDuration] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  // Audio ref for playback control
  const audioRef = useState<HTMLAudioElement | null>(null)[0];

  // Only show "text exceeds limit" toast once per exceed (not every keystroke)
  const hasShownTextLimitToastRef = useRef(false);

  // Toast hook
  const toast = useToastWithDeduplication();

  // TTS inference mutation
  const ttsMutation = useMutation({
    mutationFn: async (text: string) => {
      // Use the provided serviceId if available, otherwise fall back to language-based service ID
      const effectiveServiceId = serviceId || getServiceIdForLanguage(language);
      
      const config: TTSInferenceRequest['config'] = {
        language: { sourceLanguage: language },
        serviceId: effectiveServiceId,
        gender,
        samplingRate,
        audioFormat,
      };

      return performTTSInference(text, config);
    },
    onSuccess: (response) => {
      try {
        const audioContent = response.data.audio[0]?.audioContent;
        if (audioContent) {
          const dataUrl = `data:audio/wav;base64,${audioContent}`;
          setAudio(dataUrl);
          
          // Set response time
          setRequestTime(response.responseTime.toString());
          
          // Get audio duration
          const audioElement = new Audio(dataUrl);
          audioElement.addEventListener('loadedmetadata', () => {
            setAudioDuration(audioElement.duration);
          });
          
          setFetched(true);
          setFetching(false);
          setError(null);
        } else {
          throw new Error('No audio content received');
        }
      } catch (err) {
        console.error('Error processing TTS response:', err);
        const ttsErr = TTS_ERRORS.AUDIO_GEN_FAILED;
        setError(ttsErr.description);
        setFetching(false);
        toast({
          title: ttsErr.title,
          description: ttsErr.description,
          status: 'error',
          duration: 5000,
          isClosable: true,
        });
      }
    },
    onError: (error: any) => {
      console.error('TTS inference error:', error);
      
      // Use centralized error handler (TTS context so backend message shown as default when no specific mapping)
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error, 'tts');
      
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
      const err = TTS_ERRORS.NO_TEXT_INPUT;
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
      const err = TTS_ERRORS.EMPTY_INPUT;
      toast({
        title: err.title,
        description: err.description,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    if (trimmed.length < MIN_TTS_TEXT_LENGTH) {
      const err = TTS_ERRORS.TEXT_TOO_SHORT;
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
      const err = TTS_ERRORS.TEXT_TOO_LONG;
      toast({
        title: err.title,
        description: err.description,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    if (!VALID_TTS_CHAR_REGEX.test(trimmed)) {
      const err = TTS_ERRORS.INVALID_CHARACTERS;
      toast({
        title: err.title,
        description: err.description,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    // Validate that a service is selected
    const effectiveServiceId = serviceId || getServiceIdForLanguage(language);
    if (!effectiveServiceId) {
      toast({
        title: 'Service Required',
        description: 'Please select a TTS service.',
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
      await ttsMutation.mutateAsync(text);
    } catch (err) {
      console.error('Inference error:', err);
    }
  }, [ttsMutation, toast, serviceId, language]);

  // Set input text with validation — show toast only when first exceeding limit, not every keystroke
  const setInputTextWithValidation = useCallback((text: string) => {
    setInputText(text);

    if (text.length > MAX_TEXT_LENGTH) {
      if (!hasShownTextLimitToastRef.current) {
        hasShownTextLimitToastRef.current = true;
        const err = TTS_ERRORS.TEXT_TOO_LONG;
        toast({
          id: 'tts-text-exceeds-limit',
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

  // Set language with validation
  const setLanguageWithValidation = useCallback((newLanguage: string) => {
    setLanguage(newLanguage);
    setModelId(getServiceIdForLanguage(newLanguage));
    setInputText('');
    setAudio('');
    setFetched(false);
    setError(null);
  }, []);

  // Clear results
  const clearResults = useCallback(() => {
    setAudio('');
    setFetched(false);
    setFetching(false);
    setRequestWordCount(0);
    setRequestTime('0');
    setAudioDuration(0);
    setError(null);
  }, []);

  // Play audio
  const playAudio = useCallback(() => {
    if (audio && typeof window !== 'undefined') {
      const audioElement = new Audio(audio);
      audioElement.play().catch(err => {
        console.error('Error playing audio:', err);
        const isFormatError = err?.name === 'NotSupportedError' || err?.message?.toLowerCase().includes('format') || err?.message?.toLowerCase().includes('supported');
        const ttsErr = isFormatError ? TTS_ERRORS.AUDIO_FORMAT_ERROR : TTS_ERRORS.PLAYBACK_FAILED;
        toast({
          title: ttsErr.title,
          description: ttsErr.description,
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
      });
    }
  }, [audio, toast]);

  // Pause audio
  const pauseAudio = useCallback(() => {
    if (audioRef) {
      audioRef.pause();
    }
  }, [audioRef]);

  // Download audio
  const downloadAudio = useCallback(() => {
    if (audio) {
      try {
        const link = document.createElement('a');
        link.href = audio;
        link.download = `tts_audio_${Date.now()}.wav`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      } catch (err) {
        console.error('Error downloading audio:', err);
        const ttsErr = TTS_ERRORS.DOWNLOAD_FAILED;
        toast({
          title: ttsErr.title,
          description: ttsErr.description,
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
      }
    }
  }, [audio, toast]);

  return {
    // State
    language,
    gender,
    audioFormat,
    samplingRate,
    modelId,
    inputText,
    audio,
    fetching,
    fetched,
    requestWordCount,
    requestTime,
    audioDuration,
    error,
    
    // Methods
    performInference,
    setInputText: setInputTextWithValidation,
    setLanguage: setLanguageWithValidation,
    setGender,
    setAudioFormat,
    setSamplingRate,
    clearResults,
    playAudio,
    pauseAudio,
    downloadAudio,
  };
};
