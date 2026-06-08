// MediaRecorder lifecycle, microphone stream, and recording timer for ASR

import { useCallback, useEffect, useRef, useState, type MutableRefObject } from "react";
import { convertWebmToWav } from "../../utils/helpers";
import {
  MAX_RECORDING_DURATION,
  MIN_RECORDING_DURATION,
  RECORDING_ERRORS,
} from "../../config/constants";
import type { AsrToast } from "./shared";

export interface UseAudioRecordingOptions {
  sampleRateRef: MutableRefObject<number>;
  onAudioReady: (base64: string) => void;
  onError: (message: string | null) => void;
  toast: AsrToast;
}

export interface UseAudioRecordingReturn {
  recording: boolean;
  timer: number;
  audioStream: MediaStream | null;
  startRecording: () => Promise<void>;
  stopRecording: () => void;
  resetTimer: () => void;
}

export function useAudioRecording({
  sampleRateRef,
  onAudioReady,
  onError,
  toast,
}: UseAudioRecordingOptions): UseAudioRecordingReturn {
  const [recording, setRecording] = useState(false);
  const [audioStream, setAudioStream] = useState<MediaStream | null>(null);
  const [timer, setTimer] = useState(0);

  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<BlobPart[]>([]);
  const stopRecordingRef = useRef<(() => void) | null>(null);
  const recordingDurationRef = useRef(0);

  useEffect(() => {
    const initializeAudioStream = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        setAudioStream(stream);
        onError(null);
      } catch (err) {
        console.error("Error accessing microphone:", err);
        onError(
          "Microphone access is required to record audio. Please allow microphone permissions in your browser settings."
        );
        toast({
          title: "Microphone Access Denied",
          description:
            "Microphone access is required to record audio. Please allow microphone permissions in your browser settings.",
          status: "error",
          duration: 5000,
          isClosable: true,
        });
      }
    };

    initializeAudioStream();

    return () => {
      const currentStream = audioStream;
      if (currentStream) {
        currentStream.getTracks().forEach((track) => track.stop());
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        mediaRecorderRef.current.stop();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toast]);

  useEffect(() => {
    if (recording && timer < MAX_RECORDING_DURATION) {
      timerRef.current = setInterval(() => {
        setTimer((prev) => {
          const newTimer = prev + 1;
          if (newTimer >= MAX_RECORDING_DURATION && stopRecordingRef.current) {
            stopRecordingRef.current();
            const err = RECORDING_ERRORS.REC_TOO_LONG;
            toast({
              title: err.title,
              description: err.description,
              status: "warning",
              duration: 3000,
              isClosable: true,
            });
          }
          recordingDurationRef.current = newTimer;
          return newTimer;
        });
      }, 1000);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [recording, timer, toast]);

  const stopRecording = useCallback(() => {
    if (!mediaRecorderRef.current) {
      setRecording(false);
      return;
    }

    try {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }

      const recorder = mediaRecorderRef.current;
      if (recorder.state === "recording" || recorder.state === "paused") {
        recorder.requestData();
        recorder.stop();
      }

      setRecording(false);

      toast({
        title: "Recording stopped",
        description: "Processing audio...",
        status: "info",
        duration: 2000,
        isClosable: true,
      });

      setTimeout(() => {
        if (audioStream) {
          audioStream.getTracks().forEach((track) => {
            if (track.readyState === "live") {
              track.stop();
            }
          });
        }
      }, 500);
    } catch (err) {
      console.error("Error stopping recording:", err);
      onError("Failed to stop recording.");
      setRecording(false);
      if (audioStream) {
        audioStream.getTracks().forEach((track) => track.stop());
      }
    }
  }, [audioStream, onError, toast]);

  const startRecording = useCallback(async () => {
    let streamToUse = audioStream;
    if (!streamToUse) {
      try {
        streamToUse = await navigator.mediaDevices.getUserMedia({ audio: true });
        setAudioStream(streamToUse);
      } catch (err: unknown) {
        const error = err as { name?: string };
        const isNotFoundError =
          error?.name === "NotFoundError" || error?.name === "DevicesNotFoundError";
        toast({
          title: isNotFoundError ? "No Microphone Detected" : "Recording Error",
          description: isNotFoundError
            ? "No microphone detected. Please connect a microphone and try again."
            : "Audio stream not available. Please check microphone permissions.",
          status: "error",
          duration: 3000,
          isClosable: true,
        });
        return;
      }
    }

    const audioTracks = streamToUse.getAudioTracks();
    const hasActiveTrack = audioTracks.some((track) => track.readyState === "live");

    if (!hasActiveTrack) {
      try {
        streamToUse.getTracks().forEach((track) => track.stop());
        streamToUse = await navigator.mediaDevices.getUserMedia({ audio: true });
        setAudioStream(streamToUse);
      } catch (err: unknown) {
        const error = err as { name?: string };
        const isNotFoundError =
          error?.name === "NotFoundError" || error?.name === "DevicesNotFoundError";
        toast({
          title: isNotFoundError ? "No Microphone Detected" : "Microphone Access Denied",
          description: isNotFoundError
            ? "No microphone detected. Please connect a microphone and try again."
            : "Microphone access is required to record audio. Please allow microphone permissions in your browser settings.",
          status: "error",
          duration: 3000,
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
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    try {
      onError(null);
      setRecording(true);
      setTimer(0);
      audioChunksRef.current = [];

      const tracks = streamToUse.getAudioTracks();
      if (tracks.length === 0 || tracks.every((track) => track.readyState !== "live")) {
        const err = RECORDING_ERRORS.REC_START_FAILED;
        toast({
          title: err.title,
          description: err.description,
          status: "error",
          duration: 3000,
          isClosable: true,
        });
        setRecording(false);
        return;
      }

      const options: MediaRecorderOptions = { mimeType: "audio/webm;codecs=opus" };
      let mediaRecorder: MediaRecorder;
      let actualMimeType = "audio/webm";
      try {
        mediaRecorder = new MediaRecorder(streamToUse, options);
        actualMimeType = mediaRecorder.mimeType;
      } catch {
        mediaRecorder = new MediaRecorder(streamToUse);
        actualMimeType = mediaRecorder.mimeType || "audio/webm";
      }

      mediaRecorder.ondataavailable = (event) => {
        if (event.data?.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        try {
          const webmBlob = new Blob(audioChunksRef.current, { type: actualMimeType });
          const duration = recordingDurationRef.current;

          if (duration < MIN_RECORDING_DURATION) {
            const err = RECORDING_ERRORS.REC_TOO_SHORT;
            onError(err.description);
            setRecording(false);
            toast({
              title: err.title,
              description: err.description,
              status: "error",
              duration: 5000,
              isClosable: true,
            });
            return;
          }

          if (webmBlob.size < 1000) {
            const err = RECORDING_ERRORS.NO_AUDIO_DETECTED;
            onError(err.description);
            setRecording(false);
            toast({
              title: err.title,
              description: err.description,
              status: "error",
              duration: 5000,
              isClosable: true,
            });
            return;
          }

          let blobToSend = webmBlob;
          try {
            const targetSampleRate = sampleRateRef.current || 16000;
            const wavBlob = await convertWebmToWav(webmBlob, targetSampleRate);
            if (wavBlob?.size > 0 && wavBlob.type === "audio/wav") {
              blobToSend = wavBlob;
            } else {
              throw new Error("WAV conversion failed: invalid blob returned");
            }
          } catch (convertErr) {
            console.error("WAV conversion failed:", convertErr);
            onError("Failed to convert audio to WAV format. Please try again.");
            setRecording(false);
            toast({
              title: "Audio Conversion Error",
              description: "Failed to convert recorded audio. Please try again.",
              status: "error",
              duration: 5000,
              isClosable: true,
            });
            return;
          }

          const reader = new FileReader();
          reader.onload = () => {
            const result = reader.result as string;
            const base64Data = result?.split(",")[1];
            if (!base64Data) {
              onError("Failed to process recording.");
              setRecording(false);
              return;
            }
            onAudioReady(base64Data);
          };
          reader.onerror = () => {
            onError("Failed to process recording.");
            setRecording(false);
          };
          reader.readAsDataURL(blobToSend);
        } catch (err) {
          console.error("Error processing recording:", err);
          onError("Failed to process recording.");
          setRecording(false);
        }
      };

      mediaRecorder.onerror = () => {
        const err = RECORDING_ERRORS.REC_INTERRUPTED;
        onError(err.description);
        setRecording(false);
        toast({
          title: err.title,
          description: err.description,
          status: "error",
          duration: 3000,
          isClosable: true,
        });
      };

      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.start(1000);

      timerRef.current = setInterval(() => {
        setTimer((prev) => {
          const newTime = prev + 1;
          if (newTime >= MAX_RECORDING_DURATION && stopRecordingRef.current) {
            stopRecordingRef.current();
          }
          return newTime;
        });
      }, 1000);

      toast({
        title: "Recording started",
        description: "Speak into your microphone",
        status: "info",
        duration: 2000,
        isClosable: true,
      });
    } catch (err) {
      console.error("Error starting recording:", err);
      const recErr = RECORDING_ERRORS.REC_START_FAILED;
      onError(recErr.description);
      setRecording(false);
      toast({
        title: recErr.title,
        description: recErr.description,
        status: "error",
        duration: 3000,
        isClosable: true,
      });
    }
  }, [audioStream, onAudioReady, onError, sampleRateRef, toast]);

  useEffect(() => {
    stopRecordingRef.current = stopRecording;
  }, [stopRecording]);

  const resetTimer = useCallback(() => {
    setTimer(0);
  }, []);

  return {
    recording,
    timer,
    audioStream,
    startRecording,
    stopRecording,
    resetTimer,
  };
}
