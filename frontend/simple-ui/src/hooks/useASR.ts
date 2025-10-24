// Custom React hook for ASR functionality with recording, file upload, and inference

import { useState, useEffect, useRef, useCallback } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useToast } from '@chakra-ui/react';
import { performASRInference, transcribeAudio, ASRStreamingService } from '../services/asrService';
import { getWordCount } from '../utils/helpers';
import { UseASRReturn, ASRInferenceRequest } from '../types/asr';
import { DEFAULT_ASR_CONFIG } from '../config/constants';

// Constants
const MAX_RECORDING_DURATION = 120; // 2 minutes in seconds

// Extend Window interface for Recorder.js
declare global {
  interface Window {
    Recorder: any;
  }
}

export const useASR = (): UseASRReturn => {
  // State
  const [language, setLanguage] = useState<string>(DEFAULT_ASR_CONFIG.language);
  const [sampleRate, setSampleRate] = useState<number>(DEFAULT_ASR_CONFIG.sampleRate);
  const [inferenceMode, setInferenceMode] = useState<'rest' | 'streaming'>('rest');
  const [recording, setRecording] = useState<boolean>(false);
  const [fetching, setFetching] = useState<boolean>(false);
  const [fetched, setFetched] = useState<boolean>(false);
  const [audioText, setAudioText] = useState<string>('');
  const [responseWordCount, setResponseWordCount] = useState<number>(0);
  const [requestTime, setRequestTime] = useState<string>('0');
  const [recorder, setRecorder] = useState<any>(null);
  const [audioStream, setAudioStream] = useState<MediaStream | null>(null);
  const [timer, setTimer] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  // Refs
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const streamingServiceRef = useRef<ASRStreamingService | null>(null);

  // Toast hook
  const toast = useToast();

  // Initialize audio stream on mount
  useEffect(() => {
    const initializeAudioStream = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        setAudioStream(stream);
        setError(null);
      } catch (err) {
        console.error('Error accessing microphone:', err);
        setError('Microphone permission denied. Please enable microphone access.');
        toast({
          title: 'Microphone Access Denied',
          description: 'Please enable microphone access to use ASR recording.',
          status: 'error',
          duration: 5000,
          isClosable: true,
        });
      }
    };

    initializeAudioStream();

    // Cleanup on unmount
    return () => {
      if (audioStream) {
        audioStream.getTracks().forEach(track => track.stop());
      }
      if (audioContextRef.current) {
        audioContextRef.current.close();
      }
    };
  }, [toast]);

  // Timer effect
  useEffect(() => {
    if (recording && timer < 120) {
      timerRef.current = setInterval(() => {
        setTimer(prev => {
          const newTimer = prev + 1;
          if (newTimer >= 120) {
            stopRecording();
            toast({
              title: 'Recording Time Limit',
              description: 'Maximum recording time of 2 minutes reached.',
              status: 'warning',
              duration: 3000,
              isClosable: true,
            });
          }
          return newTimer;
        });
      }, 1000);
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [recording, timer, toast]);

  // ASR inference mutation
  const asrMutation = useMutation({
    mutationFn: async (audioContent: string) => {
      // Get serviceId based on language
      const getServiceIdForLanguage = (lang: string): string => {
        if (['hi', 'bn', 'gu', 'mr', 'pa'].includes(lang)) {
          return 'conformer-asr-multilingual';
        }
        if (['ta', 'te', 'kn', 'ml'].includes(lang)) {
          return 'conformer-asr-multilingual';
        }
        return 'whisper-large-v3'; // Fallback for other languages
      };

      const config: ASRInferenceRequest['config'] = {
        language: { sourceLanguage: language },
        serviceId: getServiceIdForLanguage(language),
        audioFormat: 'wav',
        samplingRate: sampleRate,
        transcriptionFormat: 'transcript',
        bestTokenCount: 0,
      };

      return transcribeAudio(audioContent, config);
    },
    onSuccess: (response, variables, context) => {
      const transcript = response.output[0]?.source || '';
      setAudioText(transcript);
      setResponseWordCount(getWordCount(transcript));
      setFetched(true);
      setFetching(false);
      setError(null);
    },
    onError: (error: any) => {
      console.error('ASR inference error:', error);
      setError('Failed to process audio. Please try again.');
      setFetching(false);
      toast({
        title: 'ASR Error',
        description: 'Failed to process audio. Please check your connection and try again.',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    },
  });

  // Start recording with WebSocket streaming
  const startRecording = useCallback(async () => {
    if (!audioStream || !window.Recorder) {
      toast({
        title: 'Recording Error',
        description: 'Audio stream or Recorder.js not available.',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    try {
      setError(null);
      setRecording(true);
      setTimer(0);

      // Initialize streaming service
      if (!streamingServiceRef.current) {
        streamingServiceRef.current = new ASRStreamingService();
      }

      // Connect to streaming service
      await streamingServiceRef.current.connect({
        serviceId: 'vakyansh-asr-en',
        language: language,
        samplingRate: sampleRate,
      });

      // Start streaming session
      streamingServiceRef.current.startSession({
        serviceId: 'vakyansh-asr-en',
        language: language,
        samplingRate: sampleRate,
        preProcessors: ['vad', 'denoise'],
        postProcessors: ['lm', 'punctuation'],
      });

      // Set up response handlers
      streamingServiceRef.current.onResponse((response) => {
        console.log('Streaming response:', response);
        if (response.source) {
          setAudioText(response.source);
          setResponseWordCount(getWordCount(response.source));
          setFetched(true);
        }
      });

      streamingServiceRef.current.onError((error) => {
        console.error('Streaming error:', error);
        setError('Streaming error occurred');
      });

      // Create audio context for recording
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      audioContextRef.current = audioContext;

      // Create media stream source
      const input = audioContext.createMediaStreamSource(audioStream);

      // Create recorder
      const newRecorder = new window.Recorder(input, { numChannels: 1 });
      setRecorder(newRecorder);

      // Start recording
      newRecorder.record();

      // Start timer
      timerRef.current = setInterval(() => {
        setTimer(prev => {
          const newTime = prev + 1;
          if (newTime >= MAX_RECORDING_DURATION) {
            stopRecording();
          }
          return newTime;
        });
      }, 1000);

      toast({
        title: 'Recording started',
        description: 'Speak into your microphone (streaming mode)',
        status: 'info',
        duration: 2000,
        isClosable: true,
      });
    } catch (err) {
      console.error('Error starting recording:', err);
      setError('Failed to start recording. Please try again.');
      setRecording(false);
      toast({
        title: 'Recording Error',
        description: 'Failed to start recording. Please try again.',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
    }
  }, [audioStream, language, sampleRate, toast]);

  // Perform inference
  const performInference = useCallback(async (audioContent: string) => {
    try {
      console.log('performInference called with audio content length:', audioContent.length);
      setFetching(true);
      setError(null);
      console.log('Calling asrMutation.mutateAsync...');
      await asrMutation.mutateAsync(audioContent);
      console.log('ASR mutation completed successfully');
    } catch (err) {
      console.error('Inference error:', err);
      setError('Failed to transcribe audio');
      setFetching(false);
    }
  }, [asrMutation]);

  // Handle recording completion
  const handleRecording = useCallback((blob: Blob) => {
    try {
      console.log('Recording completed, blob size:', blob.size);
      
      // Play audio
      const audioUrl = URL.createObjectURL(blob);
      const audio = new Audio(audioUrl);
      audio.play();

      // Convert to base64
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        const base64Data = result.split(',')[1];
        console.log('Base64 data length:', base64Data.length);
        console.log('Calling performInference...');
        performInference(base64Data);
      };
      reader.readAsDataURL(blob);
    } catch (err) {
      console.error('Error processing recording:', err);
      setError('Failed to process recording.');
    }
  }, [performInference]);

  // Stop recording
  const stopRecording = useCallback(() => {
    if (!recorder) return;

    try {
      recorder.stop();
      setRecording(false);

      // Clear timer
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }

      // Disconnect from streaming service
      if (streamingServiceRef.current) {
        streamingServiceRef.current.disconnect();
        streamingServiceRef.current = null;
      }

      // Export WAV for final processing
      recorder.exportWAV(handleRecording, 'audio/wav', sampleRate);

      toast({
        title: 'Recording stopped',
        description: 'Processing final audio...',
        status: 'info',
        duration: 2000,
        isClosable: true,
      });
    } catch (err) {
      console.error('Error stopping recording:', err);
      setError('Failed to stop recording.');
    }
  }, [recorder, sampleRate, handleRecording, toast]);

  // Handle file upload
  const handleFileUpload = useCallback((file: File) => {
    if (!file) return;

    try {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        const base64Data = result.split(',')[1];
        
        // Play audio
        const audio = new Audio(result);
        audio.play();
        
        performInference(base64Data);
      };
      reader.readAsDataURL(file);
    } catch (err) {
      console.error('Error processing file upload:', err);
      setError('Failed to process file upload.');
    }
  }, [performInference]);

  // Clear results
  const clearResults = useCallback(() => {
    setAudioText('');
    setResponseWordCount(0);
    setRequestTime('0');
    setFetched(false);
    setError(null);
  }, []);

  // Reset timer
  const resetTimer = useCallback(() => {
    setTimer(0);
  }, []);

  // Cleanup streaming service on unmount
  useEffect(() => {
    return () => {
      if (streamingServiceRef.current) {
        streamingServiceRef.current.disconnect();
      }
    };
  }, []);

  return {
    // State
    language,
    sampleRate,
    inferenceMode,
    recording,
    fetching,
    fetched,
    audioText,
    responseWordCount,
    requestTime,
    recorder,
    audioStream,
    timer,
    error,
    
    // Methods
    startRecording,
    stopRecording,
    handleFileUpload,
    performInference,
    setLanguage,
    setSampleRate,
    setInferenceMode,
    clearResults,
    resetTimer,
  };
};
