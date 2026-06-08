// Composes pipeline audio input and inference hooks

import { useCallback } from "react";
import { usePipelineAudio } from "./usePipelineAudio";
import { usePipelineInference } from "./usePipelineInference";

export function usePipeline() {
  const audio = usePipelineAudio();
  const inference = usePipelineInference();

  const runPipeline = useCallback(
    (
      sourceLanguage: string,
      targetLanguage: string,
      asrServiceId: string,
      nmtServiceId: string,
      ttsServiceId: string
    ) => {
      return inference.runPipeline(
        sourceLanguage,
        targetLanguage,
        asrServiceId,
        nmtServiceId,
        ttsServiceId,
        audio.pendingAudio,
        audio.pendingAudioFormat,
        () => audio.consumePendingAudio()
      );
    },
    [audio, inference]
  );

  const clearInput = useCallback(() => {
    inference.clearResult();
    audio.clearPendingAudio();
  }, [audio, inference]);

  return {
    isLoading: inference.isLoading,
    result: inference.result,
    isRecording: audio.isRecording,
    audioBlob: audio.audioBlob,
    timer: audio.timer,
    pendingAudio: audio.pendingAudio,
    clearInput,
    startRecording: audio.startRecording,
    stopRecording: audio.stopRecording,
    executePipeline: inference.executePipeline,
    processRecordedAudio: audio.processRecordedAudio,
    processUploadedAudio: audio.processUploadedAudio,
    setProcessRecordedAudioCallback: audio.setProcessRecordedAudioCallback,
    runPipeline,
  };
}
