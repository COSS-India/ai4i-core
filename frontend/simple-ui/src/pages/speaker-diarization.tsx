// Speaker Diarization — reusable service page architecture

import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  buildResponseMetadata,
  mapToServiceOptions,
  RequestContainer,
  ResponseContainer,
  ServicePageLayout,
} from "../components/service-page";
import SpeakerDiarizationResult, {
  type SpeakerDiarizationResultData,
} from "../components/service-page/results/SpeakerDiarizationResult";
import { getServicePageDefaults } from '../constants/servicePageConfig';
import { performSpeakerDiarizationInference, listSpeakerDiarizationServices } from "../services/speakerDiarizationService";
import { useAudioRecorder } from "../hooks/useAudioRecorder";
import { parseError } from "../utils/errorHandler";
import { SPEAKER_DIARIZATION_ERRORS } from '../constants';
import { showToast } from "../utils/toast";

const pageDefaults = getServicePageDefaults("speaker-diarization");

const SpeakerDiarizationPage: React.FC = () => {
  const [serviceId, setServiceId] = useState<string>("");
  const [audioData, setAudioData] = useState<string | null>(null);
  const [audioClearToken, setAudioClearToken] = useState(0);
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [result, setResult] = useState<SpeakerDiarizationResultData | null>(null);
  const [responseTime, setResponseTime] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  const { data: speakerDiarizationServices, isLoading: servicesLoading } = useQuery({
    queryKey: ["speaker-diarization-services"],
    queryFn: listSpeakerDiarizationServices,
    staleTime: 10 * 60 * 1000,
  });

  const serviceOptions = useMemo(
    () => mapToServiceOptions(speakerDiarizationServices ?? []),
    [speakerDiarizationServices]
  );

  const handleSubmit = async () => {
    if (!audioData) {
      const err = SPEAKER_DIARIZATION_ERRORS.FILE_REQUIRED;
      showToast({ type: "error", message: err.description });
      return;
    }
    if (!serviceId) {
      showToast({ type: "warning", message: "Please select a service." });
      return;
    }

    setFetching(true);
    setError(null);
    setFetched(false);
    try {
      const startTime = Date.now();
      const response = await performSpeakerDiarizationInference(audioData, serviceId);
      setResult(response.data as SpeakerDiarizationResultData);
      setResponseTime((Date.now() - startTime) / 1000);
      setFetched(true);
    } catch (err: unknown) {
      const { message: errorMessage } = parseError(err, { service: "speaker-diarization" });
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
      serviceId="speaker-diarization"
      requestPanel={
        <RequestContainer
          serviceDropdown={{
            label: "Speaker Diarization Service",
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
          result={result ? <SpeakerDiarizationResult result={result} /> : undefined}
          onClear={handleClearAudioInput}
        />
      }
    />
  );
};

export default SpeakerDiarizationPage;
