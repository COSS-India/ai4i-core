// Pipeline execution and result parsing

import { useCallback, useEffect, useRef, useState } from "react";
import { useToastWithDeduplication } from "../useToastWithDeduplication";
import { runPipelineInference } from "../../services/pipelineService";
import { base64ToAudioObjectUrl } from "../../utils/helpers";
import { getAsrTranscriptText } from "../../types/inference";
import type { PipelineInferenceRequest, PipelineResult } from "../../types/pipeline";
import { extractErrorInfo } from "../../utils/errorHandler";

export function usePipelineInference() {
  const toast = useToastWithDeduplication();
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<PipelineResult | null>(null);
  const pipelineAudioUrlRef = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      if (pipelineAudioUrlRef.current) {
        URL.revokeObjectURL(pipelineAudioUrlRef.current);
        pipelineAudioUrlRef.current = null;
      }
    };
  }, []);

  const clearResult = useCallback(() => {
    if (pipelineAudioUrlRef.current) {
      URL.revokeObjectURL(pipelineAudioUrlRef.current);
      pipelineAudioUrlRef.current = null;
    }
    setResult(null);
  }, []);

  const executePipeline = useCallback(
    async (request: PipelineInferenceRequest) => {
      setIsLoading(true);
      if (pipelineAudioUrlRef.current) {
        URL.revokeObjectURL(pipelineAudioUrlRef.current);
        pipelineAudioUrlRef.current = null;
      }
      setResult(null);

      try {
        const response = await runPipelineInference(request);
        const pipelineData = response.pipelineResponse;

        if (pipelineData.length >= 3) {
          const asrOutput = pipelineData[0].output?.[0];
          const nmtOutput = pipelineData[1].output?.[0];
          const ttsAudio = pipelineData[2].audio?.[0] || pipelineData[2].output?.[0];

          const sourceText = nmtOutput?.source || getAsrTranscriptText(asrOutput) || "";
          const targetText = nmtOutput?.target || "";
          const audioContent = ttsAudio?.audioContent || "";
          const outputAudioFormat =
            ttsAudio?.audioFormat || pipelineData[2]?.config?.audioFormat || "wav";

          let audioUrl = "";
          if (audioContent) {
            audioUrl = base64ToAudioObjectUrl(audioContent, outputAudioFormat);
            pipelineAudioUrlRef.current = audioUrl;
          }

          setResult({ sourceText, targetText, audio: audioUrl });

          toast({
            title: "Pipeline Completed",
            description: "Speech-to-Speech translation completed successfully!",
            status: "success",
            duration: 3000,
            isClosable: true,
          });
        } else {
          throw new Error("Invalid pipeline response format");
        }
      } catch (error: unknown) {
        console.error("Pipeline error:", error);
        const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(
          error,
          "pipeline"
        );
        toast({
          title: showOnlyMessage ? undefined : errorTitle,
          description: errorMessage,
          status: "error",
          duration: 5000,
          isClosable: true,
        });
      } finally {
        setIsLoading(false);
      }
    },
    [toast]
  );

  const runPipeline = useCallback(
    async (
      sourceLanguage: string,
      targetLanguage: string,
      asrServiceId: string,
      nmtServiceId: string,
      ttsServiceId: string,
      pendingAudio: string | null,
      pendingAudioFormat: string,
      onComplete?: () => void
    ) => {
      if (!pendingAudio) {
        toast({
          title: "Audio Required",
          description: "Please record or upload an audio file before running the pipeline.",
          status: "warning",
          duration: 3000,
          isClosable: true,
        });
        return;
      }

      const request: PipelineInferenceRequest = {
        pipelineTasks: [
          {
            taskType: "asr",
            config: {
              serviceId: asrServiceId,
              language: { sourceLanguage },
              audioFormat: pendingAudioFormat,
              preProcessors: ["vad", "denoiser"],
              postProcessors: ["lm", "punctuation"],
              transcriptionFormat: "transcript",
            },
          },
          {
            taskType: "translation",
            config: {
              serviceId: nmtServiceId,
              language: { sourceLanguage, targetLanguage },
            },
          },
          {
            taskType: "tts",
            config: {
              serviceId: ttsServiceId,
              language: { sourceLanguage: targetLanguage },
              gender: "male",
            },
          },
        ],
        inputData: {
          audio: [{ audioContent: pendingAudio }],
        },
        controlConfig: {
          dataTracking: false,
        },
      };

      await executePipeline(request);
      onComplete?.();
    },
    [executePipeline, toast]
  );

  return {
    isLoading,
    result,
    executePipeline,
    runPipeline,
    clearResult,
  };
}
