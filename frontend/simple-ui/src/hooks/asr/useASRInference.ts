// ASR react-query mutation, result state, and language-sync effects

import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useToastWithDeduplication } from "../useToastWithDeduplication";
import { transcribeAudio } from "../../services/asrService";
import { getWordCount } from "../../utils/helpers";
import { getAsrTranscriptText } from "../../types/inference";
import type { ASRInferenceRequest } from "../../types/asr";
import { DEFAULT_ASR_CONFIG } from "../../config/constants";
import { extractErrorInfo } from "../../utils/errorHandler";

export interface UseASRInferenceOptions {
  /** Called when a response is accepted for the current language */
  onRequestAccepted?: () => void;
}

export function useASRInference({ onRequestAccepted }: UseASRInferenceOptions = {}) {
  const toast = useToastWithDeduplication();

  const [language, setLanguage] = useState<string>(DEFAULT_ASR_CONFIG.language);
  const [sampleRate, setSampleRate] = useState<number>(DEFAULT_ASR_CONFIG.sampleRate);
  const [serviceId, setServiceId] = useState<string>(DEFAULT_ASR_CONFIG.serviceId);
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [audioText, setAudioText] = useState("");
  const [responseWordCount, setResponseWordCount] = useState(0);
  const [requestTime, setRequestTime] = useState("0");
  const [error, setError] = useState<string | null>(null);

  const languageRef = useRef(language);
  const sampleRateRef = useRef(sampleRate);
  const serviceIdRef = useRef(serviceId);
  const currentRequestLanguageRef = useRef<string | null>(null);
  const prevLanguageRef = useRef(language);
  const justCompletedRequestRef = useRef(false);

  const asrMutation = useMutation({
    mutationFn: async (audioContent: string) => {
      const config: ASRInferenceRequest["config"] = {
        language: { sourceLanguage: languageRef.current },
        serviceId: serviceIdRef.current,
        audioFormat: "wav",
        samplingRate: sampleRateRef.current,
        transcriptionFormat: "transcript",
        bestTokenCount: 0,
      };
      return transcribeAudio(audioContent, config);
    },
    onSuccess: (response) => {
      if (
        currentRequestLanguageRef.current !== null &&
        currentRequestLanguageRef.current === languageRef.current
      ) {
        const transcript = getAsrTranscriptText(response.data.output[0]);
        setAudioText(transcript);
        setResponseWordCount(getWordCount(transcript));
        setRequestTime(response.responseTime.toString());
        setFetched(true);
        setFetching(false);
        setError(null);
        onRequestAccepted?.();
        justCompletedRequestRef.current = true;
        setTimeout(() => {
          justCompletedRequestRef.current = false;
        }, 100);
      } else {
        setFetching(false);
        if (currentRequestLanguageRef.current !== languageRef.current) {
          currentRequestLanguageRef.current = null;
        }
      }
    },
    onError: (mutationError: unknown) => {
      if (
        currentRequestLanguageRef.current !== null &&
        currentRequestLanguageRef.current === languageRef.current
      ) {
        const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(
          mutationError,
          "asr"
        );
        setError(errorMessage);
        setFetching(false);
        setFetched(false);
        setAudioText("");
        setResponseWordCount(0);
        toast({
          title: showOnlyMessage ? undefined : errorTitle,
          description: errorMessage,
          status: "error",
          duration: 7000,
          isClosable: true,
        });
      } else {
        setFetching(false);
        if (currentRequestLanguageRef.current !== languageRef.current) {
          currentRequestLanguageRef.current = null;
        }
      }
    },
  });

  const performInference = useCallback(
    async (audioContent: string) => {
      try {
        const currentServiceId = serviceIdRef.current;
        const currentLanguage = languageRef.current;
        if (!currentServiceId || !currentLanguage) {
          toast({
            title: "Selection required",
            description: "Please select an ASR service and language before recording or uploading.",
            status: "warning",
            duration: 4000,
            isClosable: true,
          });
          return;
        }

        const requestLanguage = currentLanguage;
        currentRequestLanguageRef.current = requestLanguage;

        setError(null);
        setFetched(false);
        setAudioText("");
        setResponseWordCount(0);
        setFetching(true);

        await asrMutation.mutateAsync(audioContent);
      } catch (err) {
        if (
          currentRequestLanguageRef.current !== null &&
          currentRequestLanguageRef.current === languageRef.current
        ) {
          const { message: errorMessage } = extractErrorInfo(err, "asr");
          setError(errorMessage);
          setFetching(false);
          setFetched(false);
          setAudioText("");
          setResponseWordCount(0);
        }
      }
    },
    [asrMutation, toast]
  );

  const clearResultState = useCallback(() => {
    setAudioText("");
    setResponseWordCount(0);
    setRequestTime("0");
    setFetched(false);
    setError(null);
  }, []);

  useEffect(() => {
    languageRef.current = language;
  }, [language]);

  useEffect(() => {
    sampleRateRef.current = sampleRate;
  }, [sampleRate]);

  useEffect(() => {
    serviceIdRef.current = serviceId;
  }, [serviceId]);

  useEffect(() => {
    if (prevLanguageRef.current !== language) {
      if (justCompletedRequestRef.current) {
        justCompletedRequestRef.current = false;
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            if (prevLanguageRef.current !== language) {
              const oldLanguage = prevLanguageRef.current;
              prevLanguageRef.current = language;
              setAudioText("");
              setResponseWordCount(0);
              setFetched(false);
              setError(null);
              if (
                currentRequestLanguageRef.current !== null &&
                currentRequestLanguageRef.current !== language
              ) {
                currentRequestLanguageRef.current = null;
                console.log("Cancelled in-flight request for language:", oldLanguage);
              }
            }
          });
        });
        return;
      }

      const oldLanguage = prevLanguageRef.current;
      prevLanguageRef.current = language;
      setAudioText("");
      setResponseWordCount(0);
      setFetched(false);
      setError(null);
      if (
        currentRequestLanguageRef.current !== null &&
        currentRequestLanguageRef.current !== language
      ) {
        currentRequestLanguageRef.current = null;
        console.log("Cancelled in-flight request for language:", oldLanguage);
      }
    }
  }, [language]);

  return {
    language,
    sampleRate,
    serviceId,
    sampleRateRef,
    fetching,
    fetched,
    audioText,
    responseWordCount,
    requestTime,
    error,
    setLanguage,
    setSampleRate,
    setServiceId,
    setError,
    performInference,
    clearResultState,
  };
}
