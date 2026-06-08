// Composes ASR recording, upload, and inference hooks

import { useCallback, useState } from "react";
import { useToastWithDeduplication } from "../useToastWithDeduplication";
import type { UseASRReturn } from "../../types/asr";
import { useAudioRecording } from "./useAudioRecording";
import { useASRInference } from "./useASRInference";
import { useASRUpload } from "./useASRUpload";

export function useASR(): UseASRReturn {
  const toast = useToastWithDeduplication();
  const [inferenceMode, setInferenceMode] = useState<"" | "rest" | "streaming">("");
  const [pendingAudio, setPendingAudio] = useState<string | null>(null);

  const inference = useASRInference({
    onRequestAccepted: () => setPendingAudio(null),
  });

  const onRecordingAudioReady = useCallback(
    (base64: string) => {
      setPendingAudio(base64);
    },
    []
  );

  const recording = useAudioRecording({
    sampleRateRef: inference.sampleRateRef,
    onAudioReady: onRecordingAudioReady,
    onError: inference.setError,
    toast,
  });

  const resetResultState = useCallback(() => {
    inference.clearResultState();
    setPendingAudio(null);
  }, [inference]);

  const { handleFileUpload } = useASRUpload({
    toast,
    onError: inference.setError,
    onFileReady: inference.performInference,
    resetResultState: () => {
      inference.setError(null);
      inference.clearResultState();
    },
  });

  const clearResults = useCallback(() => {
    inference.clearResultState();
    setPendingAudio(null);
  }, [inference]);

  const runTranscribe = useCallback(() => {
    if (!pendingAudio) return;
    void inference.performInference(pendingAudio);
  }, [inference, pendingAudio]);

  const performInference = inference.performInference;

  const startRecording = useCallback(() => {
    setPendingAudio(null);
    void recording.startRecording();
  }, [recording]);

  return {
    language: inference.language,
    sampleRate: inference.sampleRate,
    serviceId: inference.serviceId,
    inferenceMode,
    recording: recording.recording,
    fetching: inference.fetching,
    fetched: inference.fetched,
    audioText: inference.audioText,
    responseWordCount: inference.responseWordCount,
    requestTime: inference.requestTime,
    recorder: null,
    audioStream: recording.audioStream,
    timer: recording.timer,
    error: inference.error,
    pendingAudio,

    startRecording,
    stopRecording: recording.stopRecording,
    handleFileUpload,
    performInference,
    setPendingAudio,
    runTranscribe,
    setLanguage: inference.setLanguage,
    setSampleRate: inference.setSampleRate,
    setServiceId: inference.setServiceId,
    setInferenceMode,
    clearResults,
    resetTimer: recording.resetTimer,
  };
}
