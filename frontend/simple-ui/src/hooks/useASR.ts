// Custom React hook for ASR functionality with recording, file upload, and inference

import { useState, useEffect, useRef, useCallback } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useToast } from '@chakra-ui/react';
import { performASRInference } from '../services/asrService';
import { getWordCount } from '../utils/helpers';
import { UseASRReturn, ASRInferenceRequest } from '../types/asr';
import { DEFAULT_ASR_CONFIG } from '../config/constants';

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
      const config: ASRInferenceRequest['config'] = {
        language: { sourceLanguage: language },
        serviceId: 'ai4bharat/asr-wav2vec2-indian-english',
        audioFormat: 'wav',
        encoding: 'base64',
        samplingRate: sampleRate,
      };

      return performASRInference(audioContent, config);
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

  // Start recording
  const startRecording = useCallback(() => {
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
      // Create audio context
      const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      audioContextRef.current = audioContext;

      // Create media stream source
      const input = audioContext.createMediaStreamSource(audioStream);

      // Create recorder
      const newRecorder = new window.Recorder(input, { numChannels: 1 });
      setRecorder(newRecorder);

      // Start recording
      newRecorder.record();
      setRecording(true);
      setFetching(true);
      setTimer(0);
      setError(null);
    } catch (err) {
      console.error('Error starting recording:', err);
      setError('Failed to start recording. Please try again.');
      toast({
        title: 'Recording Error',
        description: 'Failed to start recording. Please try again.',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
    }
  }, [audioStream, toast]);

  // Stop recording
  const stopRecording = useCallback(() => {
    if (!recorder) return;

    try {
      recorder.stop();
      setRecording(false);
      setFetching(false);

      // Stop audio tracks
      if (audioStream) {
        audioStream.getAudioTracks()[0].stop();
      }

      // Export WAV
      recorder.exportWAV(handleRecording, 'audio/wav', sampleRate);
    } catch (err) {
      console.error('Error stopping recording:', err);
      setError('Failed to stop recording.');
    }
  }, [recorder, audioStream, sampleRate]);

  // Handle recording completion
  const handleRecording = useCallback((blob: Blob) => {
    try {
      // Play audio
      const audioUrl = URL.createObjectURL(blob);
      const audio = new Audio(audioUrl);
      audio.play();

      // Convert to base64
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        const base64Data = result.split(',')[1];
        performInference(base64Data);
      };
      reader.readAsDataURL(blob);
    } catch (err) {
      console.error('Error processing recording:', err);
      setError('Failed to process recording.');
    }
  }, []);

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
      setFetching(true);
      setFetched(true);
    } catch (err) {
      console.error('Error processing file upload:', err);
      setError('Failed to process file upload.');
    }
  }, []);

  // Perform inference
  const performInference = useCallback(async (audioContent: string) => {
    try {
      setFetching(true);
      setError(null);
      await asrMutation.mutateAsync(audioContent);
    } catch (err) {
      console.error('Inference error:', err);
    }
  }, [asrMutation]);

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
