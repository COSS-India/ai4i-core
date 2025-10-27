// Custom hook for pipeline functionality

import { useState, useCallback, useRef } from 'react';
import { useToast } from '@chakra-ui/react';
import { runPipelineInference } from '../services/pipelineService';
import { 
  PipelineInferenceRequest, 
  PipelineResult 
} from '../types/pipeline';

export const usePipeline = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const toast = useToast();

  /**
   * Start recording audio
   */
  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioStreamRef.current = stream;

      const mediaRecorder = new MediaRecorder(stream);
      const chunks: BlobPart[] = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunks.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunks, { type: 'audio/wav' });
        setAudioBlob(blob);
        
        // Stop all tracks
        stream.getTracks().forEach(track => track.stop());
        
        setIsRecording(false);
      };

      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.start();
      setIsRecording(true);
    } catch (error) {
      console.error('Error starting recording:', error);
      toast({
        title: 'Recording Failed',
        description: 'Could not start audio recording. Please check your microphone permissions.',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    }
  }, [toast]);

  /**
   * Stop recording audio
   */
  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
    }
  }, [isRecording]);

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
      
      toast({
        title: 'Pipeline Failed',
        description: error.response?.data?.detail || error.message || 'Failed to execute pipeline',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setIsLoading(false);
    }
  }, [toast]);

  /**
   * Process recorded audio through pipeline
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
  }, [audioBlob, executePipeline, toast]);

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
    startRecording,
    stopRecording,
    executePipeline,
    processRecordedAudio,
    processUploadedAudio,
  };
};
