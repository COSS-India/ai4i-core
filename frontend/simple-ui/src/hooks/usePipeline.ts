// Custom hook for pipeline functionality

import { useState, useCallback, useRef, useEffect } from 'react';
import { useToastWithDeduplication } from './useToastWithDeduplication';
import { runPipelineInference } from '../services/pipelineService';
import { convertWebmToWav } from '../utils/helpers';
import { 
  PipelineInferenceRequest, 
  PipelineResult 
} from '../types/pipeline';
import { MAX_RECORDING_DURATION, MIN_RECORDING_DURATION, RECORDING_ERRORS, MAX_AUDIO_FILE_SIZE, UPLOAD_ERRORS, PIPELINE_ERRORS } from '../config/constants';
import { extractErrorInfo } from '../utils/errorHandler';

export const usePipeline = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [audioStream, setAudioStream] = useState<MediaStream | null>(null);
  const [timer, setTimer] = useState<number>(0);
  
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<BlobPart[]>([]);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const stopRecordingRef = useRef<(() => void) | null>(null);
  const processRecordedAudioRef = useRef<((base64Audio: string) => Promise<void>) | null>(null);
  const microphoneErrorToastShownRef = useRef(false);
  const recordingDurationRef = useRef<number>(0);
  const toast = useToastWithDeduplication();

  // Initialize audio stream on mount
  useEffect(() => {
    const initializeAudioStream = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        setAudioStream(stream);
      } catch (err: any) {
        console.error('Error accessing microphone:', err);
        if (!microphoneErrorToastShownRef.current) {
          microphoneErrorToastShownRef.current = true;
          const isNotFoundError = err?.name === 'NotFoundError' || err?.name === 'DevicesNotFoundError';
          const pipelineErr = isNotFoundError ? PIPELINE_ERRORS.MIC_NOT_FOUND : PIPELINE_ERRORS.MIC_ACCESS_DENIED;
          toast({
            title: pipelineErr.title,
            description: pipelineErr.description,
            status: 'error',
            duration: 5000,
            isClosable: true,
          });
        }
      }
    };

    initializeAudioStream();

    // Cleanup on unmount
    return () => {
      if (audioStream) {
        audioStream.getTracks().forEach(track => track.stop());
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toast]);

  // Timer effect
  useEffect(() => {
    if (isRecording && timer < MAX_RECORDING_DURATION) {
      timerRef.current = setInterval(() => {
        setTimer(prev => {
          const newTimer = prev + 1;
            if (newTimer >= MAX_RECORDING_DURATION && stopRecordingRef.current) {
            stopRecordingRef.current();
            const err = PIPELINE_ERRORS.REC_TOO_LONG;
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
  }, [isRecording, timer, toast]);

  /**
   * Start recording audio
   */
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
        if (!microphoneErrorToastShownRef.current) {
          microphoneErrorToastShownRef.current = true;
          const isNotFoundError = err?.name === 'NotFoundError' || err?.name === 'DevicesNotFoundError';
          const pipelineErr = isNotFoundError ? PIPELINE_ERRORS.MIC_NOT_FOUND : PIPELINE_ERRORS.REC_START_FAILED;
          toast({
            title: pipelineErr.title,
            description: pipelineErr.description,
            status: 'error',
            duration: 3000,
            isClosable: true,
          });
        }
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
        if (!microphoneErrorToastShownRef.current) {
          microphoneErrorToastShownRef.current = true;
          const isNotFoundError = err?.name === 'NotFoundError' || err?.name === 'DevicesNotFoundError';
          const pipelineErr = isNotFoundError ? PIPELINE_ERRORS.MIC_NOT_FOUND : PIPELINE_ERRORS.MIC_ACCESS_DENIED;
          toast({
            title: pipelineErr.title,
            description: pipelineErr.description,
            status: 'error',
            duration: 3000,
            isClosable: true,
          });
        }
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
      setIsRecording(true);
      setTimer(0);
      audioChunksRef.current = [];

      // Check if audio stream has active tracks
      const tracks = streamToUse.getAudioTracks();
      if (tracks.length === 0 || tracks.every(track => track.readyState !== 'live')) {
        console.error('No active audio tracks available');
        const err = PIPELINE_ERRORS.REC_START_FAILED;
        toast({
          title: err.title,
          description: err.description,
          status: 'error',
          duration: 3000,
          isClosable: true,
        });
        setIsRecording(false);
        setTimer(0); // Reset timer on error
        return;
      }
      
      console.log('Using audio stream with', tracks.length, 'active track(s)');

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
            const err = PIPELINE_ERRORS.NO_SPEECH_DETECTED;
            toast({
              title: err.title,
              description: err.description,
              status: 'error',
              duration: 5000,
              isClosable: true,
            });
            setIsRecording(false);
            setTimer(0); // Reset timer on error
            return;
          }
          
          // Convert WebM to WAV format (required by API config)
          let blobToStore = webmBlob;
          try {
            console.log('Converting WebM to WAV...');
            const wavBlob = await convertWebmToWav(webmBlob, 16000);
            // Check if conversion actually worked
            if (wavBlob && wavBlob.size > 0 && wavBlob.type === 'audio/wav') {
              blobToStore = wavBlob;
              console.log('WAV conversion successful, WAV blob size:', wavBlob.size);
            } else {
              console.error('WAV conversion returned invalid blob');
              throw new Error('WAV conversion failed: invalid blob returned');
            }
          } catch (convertErr) {
            console.error('WAV conversion failed:', convertErr);
            toast({
              title: 'Audio Conversion Error',
              description: 'Failed to convert recorded audio. Please try again.',
              status: 'error',
              duration: 5000,
              isClosable: true,
            });
            setIsRecording(false);
            setTimer(0); // Reset timer on error
            return;
          }
          
          // Convert blob to base64 for API and process immediately
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
            console.log(`${blobToStore.type} Base64 data length:`, base64Data.length);
            console.log('Processing recorded audio...');
            
            // Store blob for compatibility
            setAudioBlob(blobToStore);
            
            // Process the audio immediately like ASR does
            if (processRecordedAudioRef.current) {
              processRecordedAudioRef.current(base64Data);
            } else {
              console.warn('processRecordedAudioRef not set, audio blob saved but not processed');
            }
          };
          reader.onerror = (event) => {
            console.error('FileReader error:', event);
            toast({
              title: 'Recording Error',
              description: 'Failed to process recording.',
              status: 'error',
              duration: 5000,
              isClosable: true,
            });
            setIsRecording(false);
            setTimer(0);
          };
          reader.readAsDataURL(blobToStore);
          
          setIsRecording(false);
          setTimer(0); // Reset timer when recording stops
        } catch (err) {
          console.error('Error processing recording:', err);
          toast({
            title: 'Recording Error',
            description: 'Failed to process recording.',
            status: 'error',
            duration: 5000,
            isClosable: true,
          });
          setIsRecording(false);
          setTimer(0); // Reset timer on error
        }
      };

      // Handle errors
      mediaRecorder.onerror = (event) => {
        console.error('MediaRecorder error:', event);
        const err = PIPELINE_ERRORS.REC_INTERRUPTED;
        setIsRecording(false);
        setTimer(0); // Reset timer on error
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

      toast({
        title: 'Recording started',
        description: 'Speak into your microphone',
        status: 'info',
        duration: 2000,
        isClosable: true,
      });
    } catch (err) {
      console.error('Error starting recording:', err);
      const recErr = PIPELINE_ERRORS.REC_START_FAILED;
      setIsRecording(false);
      setTimer(0); // Reset timer on error
      toast({
        title: recErr.title,
        description: recErr.description,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
    }
  }, [audioStream, toast]);

  /**
   * Stop recording audio
   */
  const stopRecording = useCallback(() => {
    if (!mediaRecorderRef.current) {
      console.warn('No mediaRecorder to stop');
      setIsRecording(false);
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
      
      setIsRecording(false);

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
      setIsRecording(false);
      setTimer(0);
      
      // Force stop tracks even if there's an error
      if (audioStream) {
        audioStream.getTracks().forEach(track => track.stop());
      }
      
      toast({
        title: 'Recording Error',
        description: 'Failed to stop recording.',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
    }
  }, [audioStream, toast]);

  // Store refs for timer and processing
  useEffect(() => {
    stopRecordingRef.current = stopRecording;
  }, [stopRecording]);

  /**
   * Convert blob to base64
   */
  const blobToBase64 = (blob: Blob): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      const timeout = setTimeout(() => {
        reader.abort();
        reject(new Error('UPLOAD_TIMEOUT'));
      }, 30000); // 30 second timeout for file reading
      
      reader.onloadend = () => {
        clearTimeout(timeout);
        const result = reader.result as string;
        const base64Data = result.split(',')[1];
        if (!base64Data) {
          reject(new Error('INVALID_FILE'));
        } else {
          resolve(base64Data);
        }
      };
      reader.onerror = () => {
        clearTimeout(timeout);
        reject(new Error('INVALID_FILE'));
      };
      reader.readAsDataURL(blob);
    });
  };

  /**
   * Process audio file input
   */
  const processAudioFile = async (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      const timeout = setTimeout(() => {
        reader.abort();
        reject(new Error('UPLOAD_TIMEOUT'));
      }, 30000); // 30 second timeout for file reading
      
      reader.onloadend = () => {
        clearTimeout(timeout);
        const result = reader.result as string;
        const base64Data = result.split(',')[1];
        if (!base64Data) {
          reject(new Error('INVALID_FILE'));
        } else {
          resolve(base64Data);
        }
      };
      reader.onerror = () => {
        clearTimeout(timeout);
        reject(new Error('INVALID_FILE'));
      };
      reader.readAsDataURL(file);
    });
  };

  /**
   * Execute pipeline inference
   */
  const executePipeline = useCallback(async (
    request: PipelineInferenceRequest
  ) => {
    setIsLoading(true);
    setResult(null);

    try {
      const response = await runPipelineInference(request);

      // Parse response
      const pipelineData = response.pipelineResponse;
      
      if (pipelineData.length >= 3) {
        // Extract ASR output (index 0)
        const asrOutput = pipelineData[0].output?.[0];
        
        // Extract translation output (index 1)
        const nmtOutput = pipelineData[1].output?.[0];
        
        // Extract TTS audio (index 2)
        const ttsAudio = pipelineData[2].audio?.[0];
        
        const sourceText = nmtOutput?.source || asrOutput?.source || '';
        const targetText = nmtOutput?.target || '';
        const audioContent = ttsAudio?.audioContent || '';

        // Create audio element for duration calculation
        let audioDuration = 0;
        if (audioContent) {
          const audio = new Audio(`data:audio/wav;base64,${audioContent}`);
          audio.addEventListener('loadedmetadata', () => {
            audioDuration = audio.duration;
          });
        }

        const pipelineResult: PipelineResult = {
          sourceText,
          targetText,
          audio: audioContent ? `data:audio/wav;base64,${audioContent}` : '',
        };

        setResult(pipelineResult);
        
        toast({
          title: 'Pipeline Completed',
          description: 'Speech-to-Speech translation completed successfully!',
          status: 'success',
          duration: 3000,
          isClosable: true,
        });
      } else {
        throw new Error('Invalid pipeline response format');
      }
    } catch (error: any) {
      console.error('Pipeline error:', error);
      
      // Use centralized error handler (pipeline context so backend message shown as default when no specific mapping)
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(error, 'pipeline');
      
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMessage,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  /**
   * Process recorded audio through pipeline (internal version that takes base64)
   */
  const processRecordedAudioInternal = useCallback(async (
    base64Audio: string,
    sourceLanguage: string,
    targetLanguage: string,
    asrServiceId: string,
    nmtServiceId: string,
    ttsServiceId: string
  ) => {
    const request: PipelineInferenceRequest = {
      pipelineTasks: [
        {
          taskType: 'asr',
          config: {
            serviceId: asrServiceId,
            language: { sourceLanguage },
            audioFormat: 'wav',
            preProcessors: ['vad', 'denoiser'],
            postProcessors: ['lm', 'punctuation'],
            transcriptionFormat: 'transcript',
          },
        },
        {
          taskType: 'translation',
          config: {
            serviceId: nmtServiceId,
            language: { sourceLanguage, targetLanguage },
          },
        },
        {
          taskType: 'tts',
          config: {
            serviceId: ttsServiceId,
            language: { sourceLanguage: targetLanguage },
            gender: 'male',
          },
        },
      ],
      inputData: {
        audio: [{ audioContent: base64Audio }],
      },
      controlConfig: {
        dataTracking: false,
      },
    };

    await executePipeline(request);
  }, [executePipeline]);

  // Expose a function to set the processing callback with config
  const setProcessRecordedAudioCallback = useCallback((
    sourceLanguage: string,
    targetLanguage: string,
    asrServiceId: string,
    nmtServiceId: string,
    ttsServiceId: string
  ) => {
    processRecordedAudioRef.current = async (base64Audio: string) => {
      await processRecordedAudioInternal(base64Audio, sourceLanguage, targetLanguage, asrServiceId, nmtServiceId, ttsServiceId);
    };
  }, [processRecordedAudioInternal]);

  /**
   * Process recorded audio through pipeline (public API that takes blob)
   */
  const processRecordedAudio = useCallback(async (
    sourceLanguage: string,
    targetLanguage: string,
    asrServiceId: string,
    nmtServiceId: string,
    ttsServiceId: string
  ) => {
    if (!audioBlob) {
      toast({
        title: 'No Audio',
        description: 'Please record or upload an audio file first.',
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    const base64Audio = await blobToBase64(audioBlob);
    await processRecordedAudioInternal(base64Audio, sourceLanguage, targetLanguage, asrServiceId, nmtServiceId, ttsServiceId);
  }, [audioBlob, processRecordedAudioInternal, toast]);

  /**
   * Process uploaded audio file through pipeline
   */
  const processUploadedAudio = useCallback(async (
    file: File,
    sourceLanguage: string,
    targetLanguage: string,
    asrServiceId: string,
    nmtServiceId: string,
    ttsServiceId: string
  ) => {
    // Validate file exists
    if (!file) {
      const err = UPLOAD_ERRORS.NO_FILE_SELECTED;
      toast({
        title: err.title,
        description: err.description,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

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
      return;
    }

    // Validate file type
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
      return;
    }

    // Validate audio duration
    const validateAudioDuration = (file: File): Promise<{ isValid: boolean; duration: number; error?: string }> => {
      return new Promise((resolve) => {
        const audio = new Audio();
        const url = URL.createObjectURL(file);
        
        const timeout = setTimeout(() => {
          URL.revokeObjectURL(url);
          resolve({ isValid: false, duration: 0, error: 'UPLOAD_TIMEOUT' });
        }, 10000);
        
        audio.addEventListener('loadedmetadata', () => {
          clearTimeout(timeout);
          URL.revokeObjectURL(url);
          const duration = audio.duration;
          
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
          resolve({ isValid: false, duration: 0, error: 'INVALID_FILE' });
        });
        
        audio.src = url;
      });
    };

    try {
      const durationResult = await validateAudioDuration(file);
      if (!durationResult.isValid) {
        let err;
        switch (durationResult.error) {
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
        return;
      }

      const base64Audio = await processAudioFile(file);

      const request: PipelineInferenceRequest = {
        pipelineTasks: [
          {
            taskType: 'asr',
            config: {
              serviceId: asrServiceId,
              language: { sourceLanguage },
              audioFormat: 'wav',
              preProcessors: ['vad', 'denoiser'],
              postProcessors: ['lm', 'punctuation'],
              transcriptionFormat: 'transcript',
            },
          },
          {
            taskType: 'translation',
            config: {
              serviceId: nmtServiceId,
              language: { sourceLanguage, targetLanguage },
            },
          },
          {
            taskType: 'tts',
            config: {
              serviceId: ttsServiceId,
              language: { sourceLanguage: targetLanguage },
              gender: 'male',
            },
          },
        ],
        inputData: {
          audio: [{ audioContent: base64Audio }],
        },
        controlConfig: {
          dataTracking: false,
        },
      };

      await executePipeline(request);
    } catch (error: any) {
      console.error('Error processing uploaded audio:', error);
      const err = error?.message === 'UPLOAD_TIMEOUT' 
        ? UPLOAD_ERRORS.UPLOAD_TIMEOUT
        : error?.message === 'INVALID_FILE'
        ? UPLOAD_ERRORS.INVALID_FILE
        : UPLOAD_ERRORS.UPLOAD_FAILED;
      toast({
        title: err.title,
        description: err.description,
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
    }
  }, [executePipeline, toast]);

  return {
    isLoading,
    result,
    isRecording,
    audioBlob,
    timer,
    startRecording,
    stopRecording,
    executePipeline,
    processRecordedAudio,
    processUploadedAudio,
    setProcessRecordedAudioCallback,
  };
};
