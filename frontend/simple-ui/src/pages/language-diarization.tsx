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
import { getServicePageDefaults } from '../constants/servicePageConfig';
import { performLanguageDiarizationInference, listLanguageDiarizationServices } from "../services/languageDiarizationService";
import { parseError } from "../utils/errorHandler";
import { showToast } from "../utils/toast";

const pageDefaults = getServicePageDefaults("language-diarization");

const LanguageDiarizationPage: React.FC = () => {
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
      showToast({ type: "warning", message: "Please record or upload audio first." });
      return;
    }
    if (!serviceId) {
      showToast({ type: "warning", message: "Please select a Language Diarization service." });
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
      const { message: errorMessage } = parseError(err);
      setError(errorMessage);
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
