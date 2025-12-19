// Custom React hook for ASR functionality with recording, file upload, and inference

import { useState, useEffect, useRef, useCallback } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useToast } from '@chakra-ui/react';
import { performASRInference, transcribeAudio } from '../services/asrService';
import { getWordCount, convertWebmToWav } from '../utils/helpers';
import { UseASRReturn, ASRInferenceRequest } from '../types/asr';
import { DEFAULT_ASR_CONFIG, MAX_RECORDING_DURATION } from '../config/constants';

// MediaRecorder is a standard Web API, no need to extend Window

export const useASR = (): UseASRReturn => {
  // State
  const [language, setLanguage] = useState<string>(DEFAULT_ASR_CONFIG.language);
  const [sampleRate, setSampleRate] = useState<number>(DEFAULT_ASR_CONFIG.sampleRate);
  const [serviceId, setServiceId] = useState<string>(DEFAULT_ASR_CONFIG.serviceId);
  const [inferenceMode, setInferenceMode] = useState<'rest' | 'streaming'>('rest');
  const [recording, setRecording] = useState<boolean>(false);
  const [fetching, setFetching] = useState<boolean>(false);
  const [fetched, setFetched] = useState<boolean>(false);
  const [audioText, setAudioText] = useState<string>('');
  const [responseWordCount, setResponseWordCount] = useState<number>(0);
  const [requestTime, setRequestTime] = useState<string>('0');
  const [audioStream, setAudioStream] = useState<MediaStream | null>(null);
  const [timer, setTimer] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  // Refs
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<BlobPart[]>([]);
  const languageRef = useRef<string>(language);
  const sampleRateRef = useRef<number>(sampleRate);
  const serviceIdRef = useRef<string>(serviceId);
  const currentRequestLanguageRef = useRef<string | null>(null);
  const prevLanguageRef = useRef<string>(language);
  const justCompletedRequestRef = useRef<boolean>(false);
  const stopRecordingRef = useRef<(() => void) | null>(null);
  const performInferenceRef = useRef<((audioContent: string) => Promise<void>) | null>(null);

  // Toast hook
  const toast = useToast();

  // Initialize audio stream on mount
  useEffect(() => {
    const initializeAudioStream = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        console.log('Audio stream initialized, tracks:', stream.getAudioTracks().map(t => ({
          label: t.label,
          readyState: t.readyState,
          enabled: t.enabled,
        })));
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

    // Cleanup on unmount only
    return () => {
      // Only cleanup on component unmount, not when audioStream changes
      const currentStream = audioStream;
      if (currentStream) {
        currentStream.getTracks().forEach(track => track.stop());
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toast]); // Only run once on mount, don't include audioStream


  // Timer effect
  useEffect(() => {
    if (recording && timer < 60) {
      timerRef.current = setInterval(() => {
        setTimer(prev => {
          const newTimer = prev + 1;
          if (newTimer >= 60 && stopRecordingRef.current) {
            stopRecordingRef.current();
            toast({
              title: 'Recording Time Limit',
              description: 'Maximum recording time of 1 minute reached.',
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

  // ASR inference mutation - recreate when language, sampleRate, or serviceId changes
  const asrMutation = useMutation({
    mutationFn: async (audioContent: string) => {
      // Use ref values to ensure we always use the current language, sampleRate, and serviceId
      const currentLanguage = languageRef.current;
      const currentSampleRate = sampleRateRef.current;
      const currentServiceId = serviceIdRef.current;
      
      const config: ASRInferenceRequest['config'] = {
        language: { sourceLanguage: currentLanguage },
        serviceId: currentServiceId,
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
        const transcript = response.data.output[0]?.source || '';
        console.log('✓ Response accepted - languages match');
        console.log('Extracted transcript:', transcript);
        console.log('Transcript length:', transcript.length);
        setAudioText(transcript);
        setResponseWordCount(getWordCount(transcript));
        
        // Update request time with actual API response time (in milliseconds)
        setRequestTime(response.responseTime.toString());
        
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
        
        // Check for 401 authentication errors
        let errorMessage = 'Failed to process audio. Please try again.';
        let errorTitle = 'ASR Error';
        
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
        setFetched(false);
        setAudioText('');
        setResponseWordCount(0);
        toast({
          title: errorTitle,
          description: errorMessage,
          status: 'error',
          duration: 7000,
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

  // Start recording - use MediaRecorder API (same approach as file upload)
  const startRecording = useCallback(async () => {
    // Check and reinitialize stream if needed
    let streamToUse = audioStream;
    if (!streamToUse) {
      try {
        console.log('Audio stream not available, initializing new stream...');
        streamToUse = await navigator.mediaDevices.getUserMedia({ audio: true });
        setAudioStream(streamToUse);
      } catch (err) {
        console.error('Error reinitializing audio stream:', err);
        toast({
          title: 'Recording Error',
          description: 'Audio stream not available. Please check microphone permissions.',
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
        return;
      }
    }
    
    // Check if stream tracks are still active
    const audioTracks = streamToUse.getAudioTracks();
    const hasActiveTrack = audioTracks.some(track => track.readyState === 'live');
    
    if (!hasActiveTrack) {
      try {
        console.log('Audio stream tracks not active, reinitializing...');
        // Stop old stream
        streamToUse.getTracks().forEach(track => track.stop());
        // Get new stream
        streamToUse = await navigator.mediaDevices.getUserMedia({ audio: true });
        setAudioStream(streamToUse);
      } catch (err) {
        console.error('Error reinitializing audio stream:', err);
        toast({
          title: 'Recording Error',
          description: 'Failed to access microphone. Please check permissions.',
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
        return;
      }
    }

    // Check if MediaRecorder is supported
    if (!window.MediaRecorder) {
      toast({
        title: 'Recording Error',
        description: 'MediaRecorder API is not supported in this browser.',
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
      audioChunksRef.current = [];

      // Check if audio stream has active tracks
      const audioTracks = streamToUse.getAudioTracks();
      if (audioTracks.length === 0 || audioTracks.every(track => track.readyState !== 'live')) {
        console.error('No active audio tracks available');
        toast({
          title: 'Recording Error',
          description: 'No active audio tracks available.',
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
        setRecording(false);
        return;
      }
      
      console.log('Using audio stream with', audioTracks.length, 'active track(s)');

      // Create MediaRecorder
      const options: MediaRecorderOptions = {
        mimeType: 'audio/webm;codecs=opus' // Use webm with opus codec
      };
      
      // Fallback to default if codec not supported
      let mediaRecorder: MediaRecorder;
      let actualMimeType = 'audio/webm';
      try {
        mediaRecorder = new MediaRecorder(streamToUse, options);
        actualMimeType = mediaRecorder.mimeType;
        console.log('MediaRecorder created with mimeType:', actualMimeType);
      } catch (e) {
        console.warn('Preferred codec not supported, using default:', e);
        // Fallback to default codec
        mediaRecorder = new MediaRecorder(streamToUse);
        actualMimeType = mediaRecorder.mimeType || 'audio/webm';
        console.log('MediaRecorder created with fallback mimeType:', actualMimeType);
      }

      // Handle data available - collect chunks during recording
      mediaRecorder.ondataavailable = (event) => {
        console.log('ondataavailable event, data size:', event.data.size);
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
          console.log('Chunk added, total chunks:', audioChunksRef.current.length);
        }
      };

      // Handle recording stop
      mediaRecorder.onstop = async () => {
        try {
          console.log('MediaRecorder onstop triggered');
          console.log('Total chunks collected:', audioChunksRef.current.length);
          
          // Create blob from chunks
          const webmBlob = new Blob(audioChunksRef.current, { type: actualMimeType });
          console.log('Recording completed, WebM blob size:', webmBlob.size);
          
          // Validate blob has actual audio data (not just header)
          if (webmBlob.size < 1000) {
            console.error('Recording blob too small, likely contains no audio data');
            setError('Recording failed: No audio data captured. Please try again and ensure your microphone is working.');
            setRecording(false);
            toast({
              title: 'Recording Failed',
              description: 'No audio data was captured. Please check your microphone and try again.',
              status: 'error',
              duration: 5000,
              isClosable: true,
            });
            return;
          }
          
          // Convert WebM to WAV format (required by API config)
          // This ensures fast processing on the backend (WAV is handled directly, WebM requires ffmpeg)
          let blobToSend = webmBlob;
          try {
            console.log('Converting WebM to WAV...');
            const targetSampleRate = sampleRateRef.current || 16000;
            const wavBlob = await convertWebmToWav(webmBlob, targetSampleRate);
            // Check if conversion actually worked
            if (wavBlob && wavBlob.size > 0 && wavBlob.type === 'audio/wav') {
              blobToSend = wavBlob;
              console.log('WAV conversion successful, WAV blob size:', wavBlob.size);
            } else {
              console.error('WAV conversion returned invalid blob');
              throw new Error('WAV conversion failed: invalid blob returned');
            }
          } catch (convertErr) {
            console.error('WAV conversion failed:', convertErr);
            setError('Failed to convert audio to WAV format. Please try again.');
            setRecording(false);
            toast({
              title: 'Audio Conversion Error',
              description: 'Failed to convert recorded audio. Please try again.',
              status: 'error',
              duration: 5000,
              isClosable: true,
            });
            return;
          }
          
          // Convert blob to base64 for API
          const reader = new FileReader();
          reader.onload = () => {
            const result = reader.result as string;
            if (!result) {
              throw new Error('FileReader result is empty');
            }
            const base64Data = result.split(',')[1];
            if (!base64Data) {
              throw new Error('Failed to extract base64 data');
            }
            console.log(`${blobToSend.type} Base64 data length:`, base64Data.length);
            console.log('Calling performInference...');
            
            // Use the same approach as file upload - call performInference directly
            if (performInferenceRef.current) {
              performInferenceRef.current(base64Data);
            }
          };
          reader.onerror = (error) => {
            console.error('FileReader error:', error);
            setError('Failed to process recording.');
            setRecording(false);
          };
          reader.readAsDataURL(blobToSend);
        } catch (err) {
          console.error('Error processing recording:', err);
          setError('Failed to process recording.');
          setRecording(false);
        }
      };

      // Handle errors
      mediaRecorder.onerror = (event) => {
        console.error('MediaRecorder error:', event);
        setError('Recording error occurred.');
        setRecording(false);
        toast({
          title: 'Recording Error',
          description: 'An error occurred during recording.',
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
      };

      mediaRecorderRef.current = mediaRecorder;
      
      // Start recording with timeslice to collect chunks during recording
      // This ensures we get data even if recording is stopped quickly
      // Timeslice of 1000ms = chunks every second
      mediaRecorder.start(1000);
      console.log('MediaRecorder started with timeslice: 1000ms');

      // Start timer
      timerRef.current = setInterval(() => {
        setTimer(prev => {
          const newTime = prev + 1;
          if (newTime >= MAX_RECORDING_DURATION && stopRecordingRef.current) {
            stopRecordingRef.current();
          }
          return newTime;
        });
      }, 1000);

      toast({
        title: 'Recording started',
        description: 'Speak into your microphone',
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
  }, [audioStream, toast]);

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

  // Stop recording
  const stopRecording = useCallback(() => {
    console.log('stopRecording called, mediaRecorder state:', mediaRecorderRef.current?.state);
    
    if (!mediaRecorderRef.current) {
      console.warn('No mediaRecorder to stop');
      setRecording(false);
      return;
    }

    try {
      // Clear timer first
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      
      // Stop the MediaRecorder regardless of state
      const recorder = mediaRecorderRef.current;
      if (recorder.state === 'recording' || recorder.state === 'paused') {
        console.log('Stopping MediaRecorder...');
        // Request final data chunk before stopping
        recorder.requestData();
        recorder.stop();
        console.log('MediaRecorder stop() called, waiting for onstop handler...');
      }
      
      // IMPORTANT: Don't stop audio tracks immediately!
      // Wait for the onstop handler to complete processing the blob
      // The tracks will be stopped after processing is complete
      // Stopping tracks too early can prevent MediaRecorder from finalizing the recording
      
      setRecording(false);

      toast({
        title: 'Recording stopped',
        description: 'Processing audio...',
        status: 'info',
        duration: 2000,
        isClosable: true,
      });
      
      // Stop audio tracks after a short delay to allow MediaRecorder to finalize
      // The onstop handler will process the blob, then we can safely stop tracks
      setTimeout(() => {
        if (audioStream) {
          audioStream.getTracks().forEach(track => {
            if (track.readyState === 'live') {
              track.stop();
              console.log('Stopped audio track (after processing delay)');
            }
          });
        }
      }, 500); // Give MediaRecorder 500ms to finalize
      
      // Note: The blob processing happens in onstop handler, which is set up in startRecording
    } catch (err) {
      console.error('Error stopping recording:', err);
      setError('Failed to stop recording.');
      setRecording(false);
      
      // Force stop tracks even if there's an error
      if (audioStream) {
        audioStream.getTracks().forEach(track => track.stop());
      }
    }
  }, [toast, audioStream]);

  // Update refs whenever functions change
  useEffect(() => {
    stopRecordingRef.current = stopRecording;
  }, [stopRecording]);

  useEffect(() => {
    performInferenceRef.current = performInference;
  }, [performInference]);

  // Handle file upload
  const handleFileUpload = useCallback((file: File) => {
    if (!file) {
      console.log('handleFileUpload: No file provided');
      return;
    }

    console.log('handleFileUpload: Processing file:', file.name, 'Size:', file.size, 'Type:', file.type);

    // Validate file type - only MP3 and WAV files are supported
    const isMP3 = file.type === 'audio/mpeg' || file.type === 'audio/mp3' || file.name.toLowerCase().endsWith('.mp3');
    const isWAV = file.type === 'audio/wav' || file.type === 'audio/wave' || file.type === 'audio/x-wav' || file.name.toLowerCase().endsWith('.wav');
    
    if (!isMP3 && !isWAV) {
      toast({
        title: 'Invalid File Type',
        description: 'Only MP3 and WAV files are supported. Please select a valid audio file.',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      setError('Only MP3 and WAV files are supported. Please select a valid audio file.');
      return;
    }

    // Validate audio duration (max 1 minute)
    const validateAudioDuration = (file: File): Promise<boolean> => {
      return new Promise((resolve) => {
        const audio = new Audio();
        const url = URL.createObjectURL(file);
        
        audio.addEventListener('loadedmetadata', () => {
          URL.revokeObjectURL(url);
          const duration = audio.duration;
          console.log('Audio duration:', duration, 'seconds');
          resolve(duration <= MAX_RECORDING_DURATION);
        });
        
        audio.addEventListener('error', () => {
          URL.revokeObjectURL(url);
          console.error('Error loading audio metadata');
          // If we can't determine duration, allow it but warn user
          resolve(true);
        });
        
        audio.src = url;
      });
    };

    // Validate duration first, then process file
    validateAudioDuration(file)
      .then((isValidDuration) => {
        if (!isValidDuration) {
          toast({
            title: 'Audio Too Long',
            description: `Audio file exceeds the 1 minute limit. Please select a file that is ${MAX_RECORDING_DURATION} seconds or less.`,
            status: 'error',
            duration: 5000,
            isClosable: true,
          });
          setError(`Audio file exceeds the 1 minute limit. Please select a file that is ${MAX_RECORDING_DURATION} seconds or less.`);
          return;
        }

        // If duration is valid, proceed with file processing
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
      })
      .catch((error) => {
        console.error('Error validating audio duration:', error);
        toast({
          title: 'File Validation Error',
          description: 'Failed to validate audio file. Please try again.',
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
        setError('Failed to validate audio file. Please try again.');
      });
  }, [performInference, toast]);

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

  useEffect(() => {
    serviceIdRef.current = serviceId;
  }, [serviceId]);

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


  return {
    // State
    language,
    sampleRate,
    serviceId,
    inferenceMode,
    recording,
    fetching,
    fetched,
    audioText,
    responseWordCount,
    requestTime,
    recorder: null, // Keep for backwards compatibility but not used
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
    setServiceId,
    setInferenceMode,
    clearResults,
    resetTimer,
  };
};
