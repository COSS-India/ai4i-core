// Language Diarization — reusable service page architecture

import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  buildResponseMetadata,
  mapToServiceOptions,
  RequestContainer,
  ResponseContainer,
  ServicePageLayout,
} from "../components/service-page";
import LanguageDiarizationResult, {
  type LanguageDiarizationResultData,
} from "../components/service-page/results/LanguageDiarizationResult";
import { getServicePageDefaults } from "../config/servicePageConfig";
import { performLanguageDiarizationInference, listLanguageDiarizationServices } from "../services/languageDiarizationService";
import { useToastWithDeduplication } from "../hooks/useToastWithDeduplication";

const pageDefaults = getServicePageDefaults("language-diarization");

const LanguageDiarizationPage: React.FC = () => {
  const toast = useToastWithDeduplication();
  const [serviceId, setServiceId] = useState<string>("");
  const [audioData, setAudioData] = useState<string | null>(null);
  const [audioClearToken, setAudioClearToken] = useState(0);
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [result, setResult] = useState<LanguageDiarizationResultData | null>(null);
  const [responseTime, setResponseTime] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  const { data: languageDiarizationServices, isLoading: servicesLoading } = useQuery({
    queryKey: ["language-diarization-services"],
    queryFn: listLanguageDiarizationServices,
    staleTime: 10 * 60 * 1000,
  });

  const serviceOptions = useMemo(
    () => mapToServiceOptions(languageDiarizationServices ?? []),
    [languageDiarizationServices]
  );

  const handleSubmit = async () => {
    if (!audioData) {
      toast({
        title: "No Audio",
        description: "Please record or upload audio first.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    if (!serviceId) {
      toast({
        title: "Service Required",
        description: "Please select a Language Diarization service.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    setFetching(true);
    setError(null);
    setFetched(false);
    try {
      const startTime = Date.now();
      const response = await performLanguageDiarizationInference(audioData, serviceId);
      setResult(response.data as LanguageDiarizationResultData);
      setResponseTime((Date.now() - startTime) / 1000);
      setFetched(true);
    } catch (err: unknown) {
      let errorMessage = "Failed to perform language diarization";
      const e = err as { response?: { data?: { detail?: { message?: string }; message?: string } }; message?: string };
      if (e?.response?.data?.detail && typeof e.response.data.detail === "object" && "message" in e.response.data.detail) {
        errorMessage = (e.response.data.detail as { message: string }).message;
      } else if (e?.response?.data?.message) {
        errorMessage = e.response.data.message;
      } else if (typeof e?.response?.data?.detail === "string") {
        errorMessage = e.response.data.detail;
      } else if (e?.message) {
        errorMessage = e.message;
      }
      setError(errorMessage);
      toast({ title: "Error", description: errorMessage, status: "error", duration: 5000, isClosable: true });
    } finally {
      setFetching(false);
    }
  };

  const handleClearAudioInput = () => {
    setFetched(false);
    setResult(null);
    setAudioData(null);
    setError(null);
    setAudioClearToken((t) => t + 1);
  };

  return (
    <ServicePageLayout
      serviceId="language-diarization"
      requestPanel={
        <RequestContainer
          serviceDropdown={{
            label: "Language Diarization Service",
            value: serviceId,
            onChange: setServiceId,
            options: serviceOptions,
            loading: servicesLoading,
            disabled: fetching,
          }}
          inputType="audio"
          audioInput={{
            value: audioData,
            onChange: setAudioData,
            disabled: fetching || !serviceId,
            onClear: handleClearAudioInput,
            clearToken: audioClearToken,
            readyMessage: "Audio ready for processing.",
            showSuccessAlert: !!audioData,
          }}
          helperText={pageDefaults.helperText}
          submitButton={{
            label: pageDefaults.submitLabel,
            loadingLabel: pageDefaults.submitLoadingLabel,
            onClick: handleSubmit,
            isLoading: fetching,
            isDisabled: !audioData || !serviceId || fetching,
          }}
        />
      }
      responsePanel={
        <ResponseContainer
          fetching={fetching}
          fetchingLabel="Processing audio..."
          error={error}
          fetched={fetched}
          hasResult={!!result}
          metadata={fetched ? buildResponseMetadata({ responseTimeMs: responseTime * 1000 }) : []}
          result={result ? <LanguageDiarizationResult result={result} /> : undefined}
          onClear={handleClearAudioInput}
        />
      }
    />
  );
};

export default LanguageDiarizationPage;
