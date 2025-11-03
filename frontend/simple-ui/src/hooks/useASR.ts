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
  const languageRef = useRef<string>(language);
  const sampleRateRef = useRef<number>(sampleRate);
  const currentRequestLanguageRef = useRef<string | null>(null);
  const prevLanguageRef = useRef<string>(language);
  const justCompletedRequestRef = useRef<boolean>(false);

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

  // ASR inference mutation - recreate when language or sampleRate changes
  const asrMutation = useMutation({
    mutationFn: async (audioContent: string) => {
      // Get current language and sampleRate from state at execution time
      // Get serviceId based on language
      const getServiceIdForLanguage = (lang: string): string => {
        if (['hi', 'bn', 'gu', 'mr', 'pa'].includes(lang)) {
          return 'asr_am_ensemble';
        }
        if (['ta', 'te', 'kn', 'ml'].includes(lang)) {
          return 'asr_am_ensemble';
        }
        return 'asr_am_ensemble'; // Use asr_am_ensemble for all languages
      };

      // Use ref values to ensure we always use the current language and sampleRate
      const currentLanguage = languageRef.current;
      const currentSampleRate = sampleRateRef.current;
      
      const config: ASRInferenceRequest['config'] = {
        language: { sourceLanguage: currentLanguage },
        serviceId: getServiceIdForLanguage(currentLanguage),
        audioFormat: 'wav',
        samplingRate: currentSampleRate,
        transcriptionFormat: 'transcript',
        bestTokenCount: 0,
      };

      return transcribeAudio(audioContent, config);
    },
    onSuccess: (response, variables, context) => {
      console.log('=== ASR Success Handler ===');
      console.log('Full response:', response);
      console.log('Request language (when started):', currentRequestLanguageRef.current);
      console.log('Current language (now):', languageRef.current);
      
      // Accept response if request language matches current language
      // This means the language hasn't changed since the request started
      if (currentRequestLanguageRef.current !== null && currentRequestLanguageRef.current === languageRef.current) {
        const transcript = response.output[0]?.source || '';
        console.log('✓ Response accepted - languages match');
        console.log('Extracted transcript:', transcript);
        console.log('Transcript length:', transcript.length);
        setAudioText(transcript);
        setResponseWordCount(getWordCount(transcript));
        setFetched(true);
        setFetching(false);
        setError(null);
        // Mark that we just completed a request to prevent language change effect from clearing results
        justCompletedRequestRef.current = true;
        // Reset the flag after a short delay to allow language change effect to run if needed
        setTimeout(() => {
          justCompletedRequestRef.current = false;
        }, 100);
        console.log('States updated successfully');
      } else {
        console.log('✗ Response ignored - language mismatch or cancelled');
        console.log('  Request language:', currentRequestLanguageRef.current);
        console.log('  Current language:', languageRef.current);
        setFetching(false);
        // Clear the request language ref to allow new requests
        if (currentRequestLanguageRef.current !== languageRef.current) {
          currentRequestLanguageRef.current = null;
        }
      }
    },
    onError: (error: any) => {
      console.error('=== ASR Error Handler ===');
      console.error('Error:', error);
      console.error('Request language (when started):', currentRequestLanguageRef.current);
      console.error('Current language (now):', languageRef.current);
      
      // Accept error if request language matches current language
      if (currentRequestLanguageRef.current !== null && currentRequestLanguageRef.current === languageRef.current) {
        console.log('✓ Error accepted - languages match, showing error');
        setError('Failed to process audio. Please try again.');
        setFetching(false);
        setFetched(false);
        setAudioText('');
        setResponseWordCount(0);
        toast({
          title: 'ASR Error',
          description: 'Failed to process audio. Please check your connection and try again.',
          status: 'error',
          duration: 5000,
          isClosable: true,
        });
      } else {
        console.log('✗ Error ignored - language mismatch or cancelled');
        console.log('  Request language:', currentRequestLanguageRef.current);
        console.log('  Current language:', languageRef.current);
        setFetching(false);
        // Clear the request language ref to allow new requests
        if (currentRequestLanguageRef.current !== languageRef.current) {
          currentRequestLanguageRef.current = null;
        }
      }
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
      console.log('=== ASR Inference Start ===');
      console.log('performInference called with audio content length:', audioContent.length);
      console.log('Current language state:', language);
      console.log('Current language ref:', languageRef.current);
      
      // Track the language for this request BEFORE starting
      const requestLanguage = languageRef.current;
      currentRequestLanguageRef.current = requestLanguage;
      console.log('Request language set to:', requestLanguage);
      
      // Clear any previous errors and reset state before starting new request
      setError(null);
      setFetched(false);
      setAudioText('');
      setResponseWordCount(0);
      setFetching(true);
      
      console.log('Calling asrMutation.mutateAsync with language:', requestLanguage);
      console.log('Config will use language:', languageRef.current);
      
      const result = await asrMutation.mutateAsync(audioContent);
      console.log('ASR mutation completed, result:', result);
      
      // The onSuccess handler will check if the language matches
      // We don't need to check here since onSuccess handles it
    } catch (err) {
      console.error('=== ASR Inference Error ===');
      console.error('Inference error:', err);
      console.error('Request language:', currentRequestLanguageRef.current);
      console.error('Current language:', languageRef.current);
      
      // Only set error if this is still the current request
      if (currentRequestLanguageRef.current !== null && currentRequestLanguageRef.current === languageRef.current) {
        setError('Failed to transcribe audio');
        setFetching(false);
        setFetched(false);
        setAudioText('');
        setResponseWordCount(0);
      } else {
        console.log('Ignoring error - language changed during request');
      }
    }
  }, [asrMutation, language]);

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
    if (!file) {
      console.log('handleFileUpload: No file provided');
      return;
    }

    console.log('handleFileUpload: Processing file:', file.name, 'Size:', file.size, 'Type:', file.type);

    try {
      // Reset state before processing new file
      setError(null);
      setFetched(false);
      setAudioText('');
      setResponseWordCount(0);
      
      const reader = new FileReader();
      
      reader.onload = () => {
        try {
          const result = reader.result as string;
          if (!result) {
            throw new Error('FileReader result is empty');
          }
          const base64Data = result.split(',')[1];
          if (!base64Data) {
            throw new Error('Failed to extract base64 data');
          }
          
          console.log('File read successfully, base64 length:', base64Data.length);
          
          // Play audio preview
          try {
            const audio = new Audio(result);
            audio.play().catch(err => {
              console.log('Audio playback failed (non-critical):', err);
            });
          } catch (audioErr) {
            console.log('Audio preview not available (non-critical):', audioErr);
          }
          
          // Process the audio
          performInference(base64Data);
        } catch (err) {
          console.error('Error processing file result:', err);
          setError('Failed to process file. Please try again.');
        }
      };
      
      reader.onerror = (error) => {
        console.error('FileReader error:', error);
        setError('Failed to read the selected file.');
      };
      
      reader.onabort = () => {
        console.log('File read aborted by user');
      };
      
      console.log('Starting to read file...');
      reader.readAsDataURL(file);
    } catch (err) {
      console.error('Error processing file upload:', err);
      setError('Failed to process file upload. Please try again.');
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

  // Update refs when language or sampleRate changes
  useEffect(() => {
    const oldLanguage = languageRef.current;
    console.log('Language changed from', oldLanguage, 'to', language);
    languageRef.current = language;
    
    // If language changed while a request is in progress, cancel that request
    // by setting the request language to null so it won't match
    if (currentRequestLanguageRef.current !== null && currentRequestLanguageRef.current !== language) {
      console.log('Language changed during request - cancelling old request');
      console.log('  Old request language:', currentRequestLanguageRef.current);
      console.log('  New language:', language);
      // Don't set to null immediately - let handlers check and clear
      // This way we can see in logs what happened
    }
  }, [language]);

  useEffect(() => {
    sampleRateRef.current = sampleRate;
  }, [sampleRate]);

  // Clear results when language changes (only clear when language actually changes)
  useEffect(() => {
    // Only clear if language actually changed
    if (prevLanguageRef.current !== language) {
      // If we just completed a request, delay clearing to avoid race condition
      if (justCompletedRequestRef.current) {
        console.log('Language change detected right after request completion - delaying clear');
        justCompletedRequestRef.current = false;
        // Use requestAnimationFrame to wait until after state updates are applied
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            // Double check language still changed after state updates settle
            if (prevLanguageRef.current !== language) {
              console.log('Confirmed: Language changed from', prevLanguageRef.current, 'to', language);
              const oldLanguage = prevLanguageRef.current;
              prevLanguageRef.current = language;
              console.log('Clearing results due to language change');
              setAudioText('');
              setResponseWordCount(0);
              setFetched(false);
              setError(null);
              if (currentRequestLanguageRef.current !== null && currentRequestLanguageRef.current !== language) {
                currentRequestLanguageRef.current = null;
                console.log('Cancelled in-flight request for language:', oldLanguage);
              }
            } else {
              console.log('Language change was false alarm - not clearing results');
            }
          });
        });
        return;
      }
      
      console.log('Language changed from', prevLanguageRef.current, 'to', language);
      const oldLanguage = prevLanguageRef.current;
      prevLanguageRef.current = language;
      
      // Always clear results when language changes, regardless of fetching state
      // If a request is in progress, we'll ignore its response anyway
      console.log('Clearing results due to language change');
      setAudioText('');
      setResponseWordCount(0);
      setFetched(false);
      setError(null);
      // Clear the request language ref so any in-flight responses will be ignored
      if (currentRequestLanguageRef.current !== null && currentRequestLanguageRef.current !== language) {
        currentRequestLanguageRef.current = null;
        console.log('Cancelled in-flight request for language:', oldLanguage);
      }
    }
    // Only depend on language - this effect should only run when language changes
  }, [language]);

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
