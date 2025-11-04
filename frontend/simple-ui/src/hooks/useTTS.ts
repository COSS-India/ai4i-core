// Custom React hook for TTS functionality with text input and audio generation

import { useState, useCallback } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useToast } from '@chakra-ui/react';
import { performTTSInference } from '../services/ttsService';
import { getWordCount } from '../utils/helpers';
import { UseTTSReturn, TTSInferenceRequest, Gender, AudioFormat, SampleRate } from '../types/tts';
import { DEFAULT_TTS_CONFIG, MAX_TEXT_LENGTH } from '../config/constants';

// Helper function to get the correct service ID based on language
const getServiceIdForLanguage = (language: string): string => {
  // Dravidian languages
  if (['kn', 'ml', 'ta', 'te'].includes(language)) {
    return 'indic-tts-coqui-dravidian';
  }
  // Indo-Aryan languages (expanded as requested)
  if (['hi', 'bn', 'gu', 'mr', 'pa', 'as', 'or', 'raj'].includes(language)) {
    return 'indic-tts-coqui-indo_aryan';
  }
  // Miscellaneous languages (English, etc.)
  return 'indic-tts-coqui-misc';
};

export const useTTS = (): UseTTSReturn => {
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

  // Toast hook
  const toast = useToast();

  // TTS inference mutation
  const ttsMutation = useMutation({
    mutationFn: async (text: string) => {
      const config: TTSInferenceRequest['config'] = {
        language: { sourceLanguage: language },
        serviceId: getServiceIdForLanguage(language),
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
        setError('Failed to process audio response.');
        setFetching(false);
      }
    },
    onError: (error: any) => {
      console.error('TTS inference error:', error);
      setError('Failed to generate speech. Please try again.');
      setFetching(false);
      toast({
        title: 'TTS Error',
        description: 'Failed to generate speech. Please check your connection and try again.',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    },
  });

  // Perform inference
  const performInference = useCallback(async (text: string) => {
    if (!text || text.trim() === '') {
      toast({
        title: 'Input Required',
        description: 'Please enter text to synthesize.',
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
      setFetching(true);
      setError(null);
      setRequestWordCount(getWordCount(text));
      await ttsMutation.mutateAsync(text);
    } catch (err) {
      console.error('Inference error:', err);
    }
  }, [ttsMutation, toast]);

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
        toast({
          title: 'Playback Error',
          description: 'Failed to play audio. Please try again.',
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
        toast({
          title: 'Download Error',
          description: 'Failed to download audio. Please try again.',
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
