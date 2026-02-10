// Custom hook for audio recording functionality
import { useState, useRef, useCallback, useEffect } from 'react';
import { useToast } from '@chakra-ui/react';
import { convertWebmToWav } from '../utils/helpers';
import { MAX_RECORDING_DURATION, MIN_RECORDING_DURATION, RECORDING_ERRORS } from '../config/constants';

interface UseAudioRecorderOptions {
  sampleRate?: number;
  onRecordingComplete?: (audioBase64: string) => void;
}

export const useAudioRecorder = (options: UseAudioRecorderOptions = {}) => {
  const { sampleRate = 16000, onRecordingComplete } = options;
  const toast = useToast();
  
  const [isRecording, setIsRecording] = useState(false);
  const [timer, setTimer] = useState<number>(0);
  const [audioStream, setAudioStream] = useState<MediaStream | null>(null);
  const [recordedAudio, setRecordedAudio] = useState<string | null>(null);

  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<BlobPart[]>([]);
  const stopRecordingRef = useRef<(() => void) | null>(null);
  const recordingDurationRef = useRef<number>(0);

  // Timer effect
  useEffect(() => {
    if (isRecording && timer < MAX_RECORDING_DURATION) {
      timerRef.current = setInterval(() => {
        setTimer(prev => {
          const newTimer = prev + 1;
          recordingDurationRef.current = newTimer;
          if (newTimer >= MAX_RECORDING_DURATION) {
            if (stopRecordingRef.current) {
              stopRecordingRef.current();
            }
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
  }, [isRecording, timer]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (audioStream) {
        audioStream.getTracks().forEach(track => track.stop());
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
    };
  }, [audioStream]);

  const startRecording = useCallback(async () => {
    let streamToUse = audioStream;
    
    if (!streamToUse) {
      try {
        streamToUse = await navigator.mediaDevices.getUserMedia({ audio: true });
        setAudioStream(streamToUse);
      } catch (err: any) {
        console.error('Error accessing microphone:', err);
        const isNotFoundError = err?.name === 'NotFoundError' || err?.name === 'DevicesNotFoundError';
        toast({
          title: isNotFoundError ? 'No Microphone Detected' : 'Microphone Access Denied',
          description: isNotFoundError
            ? 'No microphone detected. Please connect a microphone and try again.'
            : 'Microphone access is required to record audio. Please allow microphone permissions in your browser settings.',
          status: 'error',
          duration: 5000,
          isClosable: true,
        });
        return;
      }
    }

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

      const options: MediaRecorderOptions = {
        mimeType: 'audio/webm;codecs=opus'
      };

      let mediaRecorder: MediaRecorder;
      let actualMimeType = 'audio/webm';
      try {
        mediaRecorder = new MediaRecorder(streamToUse, options);
        actualMimeType = mediaRecorder.mimeType;
      } catch (e) {
        mediaRecorder = new MediaRecorder(streamToUse);
        actualMimeType = mediaRecorder.mimeType || 'audio/webm';
      }

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        try {
          const webmBlob = new Blob(audioChunksRef.current, { type: actualMimeType });
          const duration = recordingDurationRef.current;

          if (duration < MIN_RECORDING_DURATION) {
            const err = RECORDING_ERRORS.REC_TOO_SHORT;
            toast({
              title: err.title,
              description: err.description,
              status: 'error',
              duration: 5000,
              isClosable: true,
            });
            setIsRecording(false);
            return;
          }

          if (webmBlob.size < 1000) {
            const err = RECORDING_ERRORS.NO_AUDIO_DETECTED;
            toast({
              title: err.title,
              description: err.description,
              status: 'error',
              duration: 5000,
              isClosable: true,
            });
            setIsRecording(false);
            return;
          }

          let blobToSend = webmBlob;
          try {
            const wavBlob = await convertWebmToWav(webmBlob, sampleRate);
            if (wavBlob && wavBlob.size > 0 && wavBlob.type === 'audio/wav') {
              blobToSend = wavBlob;
            }
          } catch (convertErr) {
            console.error('WAV conversion failed:', convertErr);
          }

          const reader = new FileReader();
          reader.onload = () => {
            const result = reader.result as string;
            if (result) {
              const base64Data = result.split(',')[1];
              if (base64Data) {
                setRecordedAudio(base64Data);
                if (onRecordingComplete) {
                  onRecordingComplete(base64Data);
                }
              }
            }
          };
          reader.onerror = () => {
            const err = RECORDING_ERRORS.REC_INTERRUPTED;
            toast({
              title: err.title,
              description: err.description,
              status: 'error',
              duration: 5000,
              isClosable: true,
            });
          };
          reader.readAsDataURL(blobToSend);
        } catch (err) {
          console.error('Error processing recording:', err);
          const recErr = RECORDING_ERRORS.REC_INTERRUPTED;
          toast({
            title: recErr.title,
            description: recErr.description,
            status: 'error',
            duration: 5000,
            isClosable: true,
          });
        } finally {
          setIsRecording(false);
          setTimer(0);
        }
      };

      mediaRecorder.onerror = (event) => {
        console.error('MediaRecorder error:', event);
        const err = RECORDING_ERRORS.REC_INTERRUPTED;
        toast({
          title: err.title,
          description: err.description,
          status: 'error',
          duration: 5000,
          isClosable: true,
        });
        setIsRecording(false);
        setTimer(0);
      };

      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.start(1000); // Collect data every second
    } catch (err) {
      console.error('Error starting recording:', err);
      const recErr = RECORDING_ERRORS.REC_START_FAILED;
      toast({
        title: recErr.title,
        description: recErr.description,
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
      setIsRecording(false);
    }
  }, [audioStream, sampleRate, onRecordingComplete, toast]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  }, []);

  // Update ref when stopRecording changes
  useEffect(() => {
    stopRecordingRef.current = stopRecording;
  }, [stopRecording]);

  return {
    isRecording,
    timer,
    recordedAudio,
    startRecording,
    stopRecording,
  };
};

