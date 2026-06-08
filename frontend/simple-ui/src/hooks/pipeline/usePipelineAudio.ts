// Pipeline audio recording, upload, and pending-input state

import { useCallback, useEffect, useRef, useState } from "react";
import { useToastWithDeduplication } from "../useToastWithDeduplication";
import { convertWebmToWav } from "../../utils/helpers";
import {
  MAX_AUDIO_FILE_SIZE,
  MAX_RECORDING_DURATION,
  RECORDING_ERRORS,
  UPLOAD_ERRORS,
  PIPELINE_ERRORS,
} from "../../config/constants";
import {
  blobToBase64,
  inferAudioFormatFromFile,
  isSupportedAudioFile,
  validateAudioDuration,
} from "./shared";

export function usePipelineAudio() {
  const toast = useToastWithDeduplication();
  const [isRecording, setIsRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [audioStream, setAudioStream] = useState<MediaStream | null>(null);
  const [timer, setTimer] = useState(0);
  const [pendingAudio, setPendingAudio] = useState<string | null>(null);
  const [pendingAudioFormat, setPendingAudioFormat] = useState("wav");

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<BlobPart[]>([]);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const stopRecordingRef = useRef<(() => void) | null>(null);
  const processRecordedAudioRef = useRef<((base64Audio: string) => Promise<void>) | null>(null);
  const microphoneErrorToastShownRef = useRef(false);
  const recordingDurationRef = useRef(0);

  const storePendingAudio = useCallback((base64: string, format = "wav") => {
    setPendingAudio(base64);
    setPendingAudioFormat(format);
  }, []);

  const consumePendingAudio = useCallback(() => {
    setPendingAudio(null);
  }, []);

  const clearPendingAudio = useCallback(() => {
    setPendingAudio(null);
    setPendingAudioFormat("wav");
    setAudioBlob(null);
    setTimer(0);
  }, []);

  useEffect(() => {
    const initializeAudioStream = async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        setAudioStream(stream);
      } catch (err: unknown) {
        console.error("Error accessing microphone:", err);
        if (!microphoneErrorToastShownRef.current) {
          microphoneErrorToastShownRef.current = true;
          const error = err as { name?: string };
          const isNotFoundError =
            error?.name === "NotFoundError" || error?.name === "DevicesNotFoundError";
          const pipelineErr = isNotFoundError
            ? PIPELINE_ERRORS.MIC_NOT_FOUND
            : PIPELINE_ERRORS.MIC_ACCESS_DENIED;
          toast({
            title: pipelineErr.title,
            description: pipelineErr.description,
            status: "error",
            duration: 5000,
            isClosable: true,
          });
        }
      }
    };

    initializeAudioStream();

    return () => {
      if (audioStream) {
        audioStream.getTracks().forEach((track) => track.stop());
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        mediaRecorderRef.current.stop();
      }
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toast]);

  useEffect(() => {
    if (isRecording && timer < MAX_RECORDING_DURATION) {
      timerRef.current = setInterval(() => {
        setTimer((prev) => {
          const newTimer = prev + 1;
          if (newTimer >= MAX_RECORDING_DURATION && stopRecordingRef.current) {
            stopRecordingRef.current();
            const err = PIPELINE_ERRORS.REC_TOO_LONG;
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
  }, [isRecording, timer, toast]);

  const stopRecording = useCallback(() => {
    if (!mediaRecorderRef.current) {
      setIsRecording(false);
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

      setIsRecording(false);

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
      setIsRecording(false);
      setTimer(0);
      if (audioStream) {
        audioStream.getTracks().forEach((track) => track.stop());
      }
      toast({
        title: "Recording Error",
        description: "Failed to stop recording.",
        status: "error",
        duration: 3000,
        isClosable: true,
      });
    }
  }, [audioStream, toast]);

  const startRecording = useCallback(async () => {
    let streamToUse = audioStream;
    if (!streamToUse) {
      try {
        streamToUse = await navigator.mediaDevices.getUserMedia({ audio: true });
        setAudioStream(streamToUse);
      } catch (err: unknown) {
        console.error("Error reinitializing audio stream:", err);
        if (!microphoneErrorToastShownRef.current) {
          microphoneErrorToastShownRef.current = true;
          const error = err as { name?: string };
          const isNotFoundError =
            error?.name === "NotFoundError" || error?.name === "DevicesNotFoundError";
          const pipelineErr = isNotFoundError
            ? PIPELINE_ERRORS.MIC_NOT_FOUND
            : PIPELINE_ERRORS.REC_START_FAILED;
          toast({
            title: pipelineErr.title,
            description: pipelineErr.description,
            status: "error",
            duration: 3000,
            isClosable: true,
          });
        }
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
        console.error("Error reinitializing audio stream:", err);
        if (!microphoneErrorToastShownRef.current) {
          microphoneErrorToastShownRef.current = true;
          const error = err as { name?: string };
          const isNotFoundError =
            error?.name === "NotFoundError" || error?.name === "DevicesNotFoundError";
          const pipelineErr = isNotFoundError
            ? PIPELINE_ERRORS.MIC_NOT_FOUND
            : PIPELINE_ERRORS.MIC_ACCESS_DENIED;
          toast({
            title: pipelineErr.title,
            description: pipelineErr.description,
            status: "error",
            duration: 3000,
            isClosable: true,
          });
        }
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
      setIsRecording(true);
      setTimer(0);
      audioChunksRef.current = [];

      const tracks = streamToUse.getAudioTracks();
      if (tracks.length === 0 || tracks.every((track) => track.readyState !== "live")) {
        const err = PIPELINE_ERRORS.REC_START_FAILED;
        toast({
          title: err.title,
          description: err.description,
          status: "error",
          duration: 3000,
          isClosable: true,
        });
        setIsRecording(false);
        setTimer(0);
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

          if (webmBlob.size < 1000) {
            const err = PIPELINE_ERRORS.NO_SPEECH_DETECTED;
            toast({
              title: err.title,
              description: err.description,
              status: "error",
              duration: 5000,
              isClosable: true,
            });
            setIsRecording(false);
            setTimer(0);
            return;
          }

          let blobToStore = webmBlob;
          try {
            const wavBlob = await convertWebmToWav(webmBlob, 16000);
            if (wavBlob?.size > 0 && wavBlob.type === "audio/wav") {
              blobToStore = wavBlob;
            } else {
              throw new Error("WAV conversion failed: invalid blob returned");
            }
          } catch (convertErr) {
            console.error("WAV conversion failed:", convertErr);
            toast({
              title: "Audio Conversion Error",
              description: "Failed to convert recorded audio. Please try again.",
              status: "error",
              duration: 5000,
              isClosable: true,
            });
            setIsRecording(false);
            setTimer(0);
            return;
          }

          const reader = new FileReader();
          reader.onload = () => {
            const fileResult = reader.result as string;
            const base64Data = fileResult?.split(",")[1];
            if (!base64Data) {
              toast({
                title: "Recording Error",
                description: "Failed to process recording.",
                status: "error",
                duration: 5000,
                isClosable: true,
              });
              return;
            }
            setAudioBlob(blobToStore);
            void processRecordedAudioRef.current?.(base64Data);
          };
          reader.onerror = () => {
            toast({
              title: "Recording Error",
              description: "Failed to process recording.",
              status: "error",
              duration: 5000,
              isClosable: true,
            });
            setIsRecording(false);
            setTimer(0);
          };
          reader.readAsDataURL(blobToStore);

          setIsRecording(false);
          setTimer(0);
        } catch (err) {
          console.error("Error processing recording:", err);
          toast({
            title: "Recording Error",
            description: "Failed to process recording.",
            status: "error",
            duration: 5000,
            isClosable: true,
          });
          setIsRecording(false);
          setTimer(0);
        }
      };

      mediaRecorder.onerror = () => {
        const err = PIPELINE_ERRORS.REC_INTERRUPTED;
        setIsRecording(false);
        setTimer(0);
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

      toast({
        title: "Recording started",
        description: "Speak into your microphone",
        status: "info",
        duration: 2000,
        isClosable: true,
      });
    } catch (err) {
      console.error("Error starting recording:", err);
      const recErr = PIPELINE_ERRORS.REC_START_FAILED;
      setIsRecording(false);
      setTimer(0);
      toast({
        title: recErr.title,
        description: recErr.description,
        status: "error",
        duration: 3000,
        isClosable: true,
      });
    }
  }, [audioStream, toast]);

  useEffect(() => {
    stopRecordingRef.current = stopRecording;
  }, [stopRecording]);

  const processRecordedAudioInternal = useCallback(
    async (base64Audio: string) => {
      storePendingAudio(base64Audio, "wav");
    },
    [storePendingAudio]
  );

  const setProcessRecordedAudioCallback = useCallback(
    (
      _sourceLanguage: string,
      _targetLanguage: string,
      _asrServiceId: string,
      _nmtServiceId: string,
      _ttsServiceId: string
    ) => {
      processRecordedAudioRef.current = async (base64Audio: string) => {
        await processRecordedAudioInternal(base64Audio);
      };
    },
    [processRecordedAudioInternal]
  );

  const processRecordedAudio = useCallback(
    async (
      _sourceLanguage: string,
      _targetLanguage: string,
      _asrServiceId: string,
      _nmtServiceId: string,
      _ttsServiceId: string
    ) => {
      if (!audioBlob) {
        toast({
          title: "No Audio",
          description: "Please record or upload an audio file first.",
          status: "warning",
          duration: 3000,
          isClosable: true,
        });
        return;
      }
      const base64Audio = await blobToBase64(audioBlob);
      await processRecordedAudioInternal(base64Audio);
    },
    [audioBlob, processRecordedAudioInternal, toast]
  );

  const processUploadedAudio = useCallback(
    async (
      file: File,
      _sourceLanguage: string,
      _targetLanguage: string,
      _asrServiceId: string,
      _nmtServiceId: string,
      _ttsServiceId: string
    ) => {
      if (!file) {
        const err = UPLOAD_ERRORS.NO_FILE_SELECTED;
        toast({
          title: err.title,
          description: err.description,
          status: "error",
          duration: 3000,
          isClosable: true,
        });
        return;
      }

      if (!isSupportedAudioFile(file)) {
        const err =
          file.size > MAX_AUDIO_FILE_SIZE
            ? UPLOAD_ERRORS.FILE_TOO_LARGE
            : UPLOAD_ERRORS.UNSUPPORTED_FORMAT;
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
        const durationResult = await validateAudioDuration(file);
        if (!durationResult.isValid) {
          let err;
          switch (durationResult.error) {
            case "AUDIO_TOO_SHORT":
              err = UPLOAD_ERRORS.AUDIO_TOO_SHORT;
              break;
            case "AUDIO_TOO_LONG":
              err = UPLOAD_ERRORS.AUDIO_TOO_LONG;
              break;
            case "EMPTY_AUDIO_FILE":
              err = UPLOAD_ERRORS.EMPTY_AUDIO_FILE;
              break;
            case "UPLOAD_TIMEOUT":
              err = UPLOAD_ERRORS.UPLOAD_TIMEOUT;
              break;
            default:
              err = UPLOAD_ERRORS.INVALID_FILE;
              break;
          }
          toast({
            title: err.title,
            description: err.description,
            status: "error",
            duration: 5000,
            isClosable: true,
          });
          return;
        }

        let fileToEncode: Blob = file;
        let formatToUse = inferAudioFormatFromFile(file);
        try {
          const normalizedWav = await convertWebmToWav(file, 16000);
          if (normalizedWav?.size > 0) {
            fileToEncode = normalizedWav;
            formatToUse = "wav";
          }
        } catch (conversionError) {
          console.warn("Pipeline upload WAV conversion failed, using original format:", conversionError);
        }

        const base64Audio = await blobToBase64(fileToEncode);
        storePendingAudio(base64Audio, formatToUse);
      } catch (error: unknown) {
        console.error("Error processing uploaded audio:", error);
        const message = error instanceof Error ? error.message : "";
        const err =
          message === "UPLOAD_TIMEOUT"
            ? UPLOAD_ERRORS.UPLOAD_TIMEOUT
            : message === "INVALID_FILE"
              ? UPLOAD_ERRORS.INVALID_FILE
              : UPLOAD_ERRORS.UPLOAD_FAILED;
        toast({
          title: err.title,
          description: err.description,
          status: "error",
          duration: 3000,
          isClosable: true,
        });
      }
    },
    [storePendingAudio, toast]
  );

  return {
    isRecording,
    audioBlob,
    timer,
    pendingAudio,
    pendingAudioFormat,
    startRecording,
    stopRecording,
    processRecordedAudio,
    processUploadedAudio,
    setProcessRecordedAudioCallback,
    consumePendingAudio,
    clearPendingAudio,
  };
}
