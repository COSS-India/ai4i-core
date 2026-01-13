// Custom hook for pipeline functionality

import { useState, useCallback, useRef, useEffect } from 'react';
import { useToast } from '@chakra-ui/react';
import { runPipelineInference } from '../services/pipelineService';
import { convertWebmToWav } from '../utils/helpers';
import { 
  PipelineInferenceRequest, 
  PipelineResult 
} from '../types/pipeline';
import { MAX_RECORDING_DURATION } from '../config/constants';
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
  const toast = useToast();

  // Initialize audio stream on mount
  useEffect(() => {
    const initializeAudioStream = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        setAudioStream(stream);
      } catch (err) {
        console.error('Error accessing microphone:', err);
        toast({
          title: 'Microphone Access Denied',
          description: 'Please enable microphone access to use recording.',
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
            toast({
              title: 'Recording Time Limit',
              description: 'Maximum recording time reached.',
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
      setIsRecording(true);
      setTimer(0);
      audioChunksRef.current = [];

      // Check if audio stream has active tracks
      const tracks = streamToUse.getAudioTracks();
      if (tracks.length === 0 || tracks.every(track => track.readyState !== 'live')) {
        console.error('No active audio tracks available');
        toast({
          title: 'Recording Error',
          description: 'No active audio tracks available.',
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
            toast({
              title: 'Recording Failed',
              description: 'No audio data was captured. Please check your microphone and try again.',
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
        setIsRecording(false);
        setTimer(0); // Reset timer on error
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

      toast({
        title: 'Recording started',
        description: 'Speak into your microphone',
        status: 'info',
        duration: 2000,
        isClosable: true,
      });
    } catch (err) {
      console.error('Error starting recording:', err);
      setIsRecording(false);
      setTimer(0); // Reset timer on error
      toast({
        title: 'Recording Error',
        description: 'Failed to start recording. Please try again.',
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
      reader.onloadend = () => {
        const result = reader.result as string;
        const base64Data = result.split(',')[1];
        resolve(base64Data);
      };
      reader.onerror = reject;
      reader.readAsDataURL(blob);
    });
  };

  /**
   * Process audio file input
   */
  const processAudioFile = async (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const result = reader.result as string;
        const base64Data = result.split(',')[1];
        resolve(base64Data);
      };
      reader.onerror = reject;
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
      
      // Use centralized error handler
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(error);
      
      toast({
        title: errorTitle,
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
  }, [executePipeline]);

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
