// Custom React hook for ASR functionality with recording, file upload, and inference

import { useState, useEffect, useRef, useCallback } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useToast } from '@chakra-ui/react';
import { performASRInference, transcribeAudio } from '../services/asrService';
import { getWordCount, convertWebmToWav } from '../utils/helpers';
import { UseASRReturn, ASRInferenceRequest } from '../types/asr';
import { DEFAULT_ASR_CONFIG, MAX_RECORDING_DURATION, MIN_RECORDING_DURATION, RECORDING_ERRORS, MAX_AUDIO_FILE_SIZE, UPLOAD_ERRORS } from '../config/constants';
import { extractErrorInfo } from '../utils/errorHandler';

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
  const recordingDurationRef = useRef<number>(0);

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
        setError('Microphone access is required to record audio. Please allow microphone permissions in your browser settings.');
        toast({
          title: 'Microphone Access Denied',
          description: 'Microphone access is required to record audio. Please allow microphone permissions in your browser settings.',
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
    if (recording && timer < MAX_RECORDING_DURATION) {
      timerRef.current = setInterval(() => {
        setTimer(prev => {
          const newTimer = prev + 1;
          if (newTimer >= MAX_RECORDING_DURATION && stopRecordingRef.current) {
            stopRecordingRef.current();
            const err = RECORDING_ERRORS.REC_TOO_LONG;
            toast({
              title: err.title,
              description: err.description,
              status: 'warning',
              duration: 3000,
              isClosable: true,
            });
          }
          recordingDurationRef.current = newTimer;
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
        
        // Use centralized error handler (asr context so backend message shown as default when no specific mapping)
        const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error, 'asr');
        
        setError(errorMessage);
        setFetching(false);
        setFetched(false);
        setAudioText('');
        setResponseWordCount(0);
        toast({
          title: showOnlyMessage ? undefined : errorTitle,
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
      } catch (err: any) {
        console.error('Error reinitializing audio stream:', err);
        const isNotFoundError = err?.name === 'NotFoundError' || err?.name === 'DevicesNotFoundError';
        toast({
          title: isNotFoundError ? 'No Microphone Detected' : 'Recording Error',
          description: isNotFoundError 
            ? 'No microphone detected. Please connect a microphone and try again.'
            : 'Audio stream not available. Please check microphone permissions.',
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
      } catch (err: any) {
        console.error('Error reinitializing audio stream:', err);
        const isNotFoundError = err?.name === 'NotFoundError' || err?.name === 'DevicesNotFoundError';
        toast({
          title: isNotFoundError ? 'No Microphone Detected' : 'Microphone Access Denied',
          description: isNotFoundError
            ? 'No microphone detected. Please connect a microphone and try again.'
            : 'Microphone access is required to record audio. Please allow microphone permissions in your browser settings.',
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
        return;
      }
    }

    // Check if MediaRecorder is supported
    if (!window.MediaRecorder) {
      const err = RECORDING_ERRORS.BROWSER_NOT_SUPPORTED;
      toast({
        title: err.title,
        description: err.description,
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
        const err = RECORDING_ERRORS.REC_START_FAILED;
        toast({
          title: err.title,
          description: err.description,
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
          
          // Check minimum recording duration
          const duration = recordingDurationRef.current;
          if (duration < MIN_RECORDING_DURATION) {
            const err = RECORDING_ERRORS.REC_TOO_SHORT;
            setError(err.description);
            setRecording(false);
            toast({
              title: err.title,
              description: err.description,
              status: 'error',
              duration: 5000,
              isClosable: true,
            });
            return;
          }

          // Validate blob has actual audio data (not just header)
          if (webmBlob.size < 1000) {
            console.error('Recording blob too small, likely contains no audio data');
            const err = RECORDING_ERRORS.NO_AUDIO_DETECTED;
            setError(err.description);
            setRecording(false);
            toast({
              title: err.title,
              description: err.description,
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
        const err = RECORDING_ERRORS.REC_INTERRUPTED;
        setError(err.description);
        setRecording(false);
        toast({
          title: err.title,
          description: err.description,
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
      const recErr = RECORDING_ERRORS.REC_START_FAILED;
      setError(recErr.description);
      setRecording(false);
      toast({
        title: recErr.title,
        description: recErr.description,
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
      // State and toast are already handled by the mutation's onError; only update state
      // here in case onError was skipped (e.g. language mismatch). Do not show a second toast.
      if (currentRequestLanguageRef.current !== null && currentRequestLanguageRef.current === languageRef.current) {
        const { message: errorMessage } = extractErrorInfo(err, 'asr');
        setError(errorMessage);
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
      const err = UPLOAD_ERRORS.NO_FILE_SELECTED;
      toast({
        title: err.title,
        description: err.description,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      setError(err.description);
      return;
    }

    console.log('handleFileUpload: Processing file:', file.name, 'Size:', file.size, 'Type:', file.type);

    // Validate file size
    if (file.size > MAX_AUDIO_FILE_SIZE) {
      const err = UPLOAD_ERRORS.FILE_TOO_LARGE;
      toast({
        title: err.title,
        description: err.description,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      setError(err.description);
      return;
    }

    // Validate file type - only MP3 and WAV files are supported
    const isMP3 = file.type === 'audio/mpeg' || file.type === 'audio/mp3' || file.name.toLowerCase().endsWith('.mp3');
    const isWAV = file.type === 'audio/wav' || file.type === 'audio/wave' || file.type === 'audio/x-wav' || file.name.toLowerCase().endsWith('.wav');
    
    if (!isMP3 && !isWAV) {
      const err = UPLOAD_ERRORS.UNSUPPORTED_FORMAT;
      toast({
        title: err.title,
        description: err.description,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      setError(err.description);
      return;
    }

    // Validate audio duration (min 1 second, max 60 seconds)
    const validateAudioDuration = (file: File): Promise<{ isValid: boolean; duration: number; error?: string }> => {
      return new Promise((resolve) => {
        const audio = new Audio();
        const url = URL.createObjectURL(file);
        
        const timeout = setTimeout(() => {
          URL.revokeObjectURL(url);
          resolve({ isValid: false, duration: 0, error: 'UPLOAD_TIMEOUT' });
        }, 10000); // 10 second timeout
        
        audio.addEventListener('loadedmetadata', () => {
          clearTimeout(timeout);
          URL.revokeObjectURL(url);
          const duration = audio.duration;
          console.log('Audio duration:', duration, 'seconds');
          
          if (duration < MIN_RECORDING_DURATION) {
            resolve({ isValid: false, duration, error: 'AUDIO_TOO_SHORT' });
          } else if (duration > MAX_RECORDING_DURATION) {
            resolve({ isValid: false, duration, error: 'AUDIO_TOO_LONG' });
          } else if (isNaN(duration) || duration === 0) {
            resolve({ isValid: false, duration, error: 'EMPTY_AUDIO_FILE' });
          } else {
            resolve({ isValid: true, duration });
          }
        });
        
        audio.addEventListener('error', () => {
          clearTimeout(timeout);
          URL.revokeObjectURL(url);
          console.error('Error loading audio metadata');
          resolve({ isValid: false, duration: 0, error: 'INVALID_FILE' });
        });
        
        audio.src = url;
      });
    };

    // Validate duration first, then process file
    validateAudioDuration(file)
      .then((result) => {
        if (!result.isValid) {
          let err;
          switch (result.error) {
            case 'AUDIO_TOO_SHORT':
              err = UPLOAD_ERRORS.AUDIO_TOO_SHORT;
              break;
            case 'AUDIO_TOO_LONG':
              err = UPLOAD_ERRORS.AUDIO_TOO_LONG;
              break;
            case 'EMPTY_AUDIO_FILE':
              err = UPLOAD_ERRORS.EMPTY_AUDIO_FILE;
              break;
            case 'UPLOAD_TIMEOUT':
              err = UPLOAD_ERRORS.UPLOAD_TIMEOUT;
              break;
            case 'INVALID_FILE':
            default:
              err = UPLOAD_ERRORS.INVALID_FILE;
              break;
          }
          toast({
            title: err.title,
            description: err.description,
            status: 'error',
            duration: 5000,
            isClosable: true,
          });
          setError(err.description);
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
            const err = UPLOAD_ERRORS.INVALID_FILE;
            toast({
              title: err.title,
              description: err.description,
              status: 'error',
              duration: 3000,
              isClosable: true,
            });
            setError(err.description);
          };
          
          reader.onabort = () => {
            console.log('File read aborted by user');
          };
          
          console.log('Starting to read file...');
          reader.readAsDataURL(file);
        } catch (err) {
          console.error('Error processing file upload:', err);
          const uploadErr = UPLOAD_ERRORS.UPLOAD_FAILED;
          toast({
            title: uploadErr.title,
            description: uploadErr.description,
            status: 'error',
            duration: 3000,
            isClosable: true,
          });
          setError(uploadErr.description);
        }
      })
      .catch((error) => {
        console.error('Error validating audio duration:', error);
        const err = UPLOAD_ERRORS.INVALID_FILE;
        toast({
          title: err.title,
          description: err.description,
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
        setError(err.description);
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
