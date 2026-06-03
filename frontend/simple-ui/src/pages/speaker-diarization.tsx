// Speaker Diarization — reusable service page architecture

import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AudioInputSection,
  buildResponseMetadata,
  mapToServiceOptions,
  RequestContainer,
  ResponseContainer,
  ServicePageLayout,
} from "../components/service-page";
import SpeakerDiarizationResult, {
  type SpeakerDiarizationResultData,
} from "../components/service-page/results/SpeakerDiarizationResult";
import { getServicePageDefaults } from "../config/servicePageConfig";
import { performSpeakerDiarizationInference, listSpeakerDiarizationServices } from "../services/speakerDiarizationService";
import { useAudioRecorder } from "../hooks/useAudioRecorder";
import { extractErrorInfo } from "../utils/errorHandler";
import { SPEAKER_DIARIZATION_ERRORS } from "../config/constants";
import { useToastWithDeduplication } from "../hooks/useToastWithDeduplication";

const pageDefaults = getServicePageDefaults("speaker-diarization");

const SpeakerDiarizationPage: React.FC = () => {
  const toast = useToastWithDeduplication();
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

  const { isRecording, timer, startRecording, stopRecording } = useAudioRecorder({
    sampleRate: 16000,
    onRecordingComplete: (audioBase64: string) => {
      setAudioData(audioBase64);
      toast({
        title: "Recording Complete",
        description: "Audio recorded successfully. Click Submit to process.",
        status: "success",
        duration: 3000,
        isClosable: true,
      });
    },
  });

  const handleRecordingChange = (recording: boolean) => {
    if (recording) startRecording();
    else stopRecording();
  };

  const handleAudioReady = (audioBase64: string) => {
    setAudioData(audioBase64);
    toast({
      title: "Audio Ready",
      description: "Audio file loaded. Click Submit to process.",
      status: "success",
      duration: 3000,
      isClosable: true,
    });
  };

  const handleSubmit = async () => {
    if (!audioData) {
      const err = SPEAKER_DIARIZATION_ERRORS.FILE_REQUIRED;
      toast({ title: err.title, description: err.description, status: "error", duration: 3000, isClosable: true });
      return;
    }
    if (!serviceId) {
      toast({ title: "Service Required", description: "Please select a service.", status: "warning", duration: 3000, isClosable: true });
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
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(err, "speaker-diarization");
      setError(errorMessage);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
        description: errorMessage,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
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
            children: (
              <AudioInputSection
                audioData={audioData}
                isRecording={isRecording}
                onAudioReady={handleAudioReady}
                onRecordingChange={handleRecordingChange}
                disabled={fetching || !serviceId}
                timer={timer}
                onClear={handleClearAudioInput}
                clearToken={audioClearToken}
                readyMessage="Audio ready for processing."
                showSuccessAlert={!!audioData}
              />
            ),
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
