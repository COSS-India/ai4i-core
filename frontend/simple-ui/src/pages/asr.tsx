// ASR service testing page — reusable service page architecture

import { FormControl, FormLabel, Select } from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import React, { useMemo } from "react";
import { FaFileAlt } from "react-icons/fa";
import {
  buildResponseMetadata,
  GuestUsageLimitBanner,
  mapToServiceOptions,
  RequestContainer,
  ResponseContainer,
  ServicePageLayout,
  useCopyToClipboard,
} from "../components/service-page";
import { ASR_SUPPORTED_LANGUAGES } from '../constants';
import { getServicePageDefaults } from '../constants/servicePageConfig';
import { useASR } from "../hooks/useASR";
import { listASRServices } from "../services/asrService";

const pageDefaults = getServicePageDefaults("asr");
const languageOptions = ASR_SUPPORTED_LANGUAGES.map((l) => ({ code: l.code, label: l.label }));

const ASRPage: React.FC = () => {
  const { copy, download } = useCopyToClipboard();
  const [audioClearToken, setAudioClearToken] = React.useState(0);
  const {
    language,
    serviceId,
    inferenceMode,
    recording,
    fetching,
    fetched,
    audioText,
    responseWordCount,
    requestTime,
    timer,
    error,
    pendingAudio,
    setPendingAudio,
    startRecording,
    stopRecording,
    runTranscribe,
    setLanguage,
    setServiceId,
    setInferenceMode,
    clearResults,
  } = useASR();

  const handleClearAudioInput = () => {
    clearResults();
    setAudioClearToken((t) => t + 1);
  };

  const { data: asrServices, isLoading: servicesLoading } = useQuery({
    queryKey: ["asr-services"],
    queryFn: listASRServices,
    staleTime: 5 * 60 * 1000,
  });

  const serviceOptions = useMemo(
    () => mapToServiceOptions(asrServices ?? []),
    [asrServices]
  );

  const handleRecordingChange = (isRecording: boolean) => {
    if (isRecording) startRecording();
    else stopRecording();
  };

  const canTranscribe =
    !!pendingAudio && !!serviceId?.trim() && !!language?.trim() && !fetching;

  const metadata = buildResponseMetadata({
    responseWordCount,
    responseTimeMs: Number(requestTime),
  });

  return (
    <ServicePageLayout
      serviceId="asr"
      headDescription="Test Automatic Speech Recognition with microphone recording and file upload"
      banner={<GuestUsageLimitBanner />}
      requestPanel={
        <RequestContainer
          inputType="audio"
          topSlot={
            <FormControl mt={0} pt={0}>
              <FormLabel className="dview-service-try-option-title" mt={0}>
                Inference Mode
              </FormLabel>
              <Select
                value={inferenceMode}
                onChange={(e) =>
                  setInferenceMode(e.target.value as "" | "rest" | "streaming")
                }
                placeholder="Select"
              >
                <option value="rest">REST API</option>
                <option value="streaming">WebSocket Streaming</option>
              </Select>
            </FormControl>
          }
          serviceDropdown={{
            label: "ASR Service",
            value: serviceId,
            onChange: setServiceId,
            options: serviceOptions,
            loading: servicesLoading,
            disabled: fetching,
          }}
          languageConfig={{
            mode: "source-only",
            sourceLanguage: language,
            onSourceChange: setLanguage,
            sourceOptions: languageOptions,
            disabled: fetching,
          }}
          audioInput={{
            value: pendingAudio,
            onChange: setPendingAudio,
            isRecording: recording,
            onRecordingChange: handleRecordingChange,
            timer,
            disabled: fetching || !serviceId || !language,
            onClear: handleClearAudioInput,
            clearToken: audioClearToken,
            readyMessage:
              "Audio ready (recording or upload). Click Transcribe to generate the transcript.",
          }}
          helperText={pageDefaults.helperText}
          submitButton={{
            label: pageDefaults.submitLabel,
            loadingLabel: pageDefaults.submitLoadingLabel,
            onClick: runTranscribe,
            isLoading: fetching,
            isDisabled: !canTranscribe,
            icon: <FaFileAlt />,
          }}
        />
      }
      responsePanel={
        <ResponseContainer
          fetching={fetching}
          fetchingLabel="Processing audio..."
          error={error}
          fetched={fetched}
          hasResult={!!audioText}
          resultTitle="Transcript"
          resultContent={audioText}
          metadata={fetched && audioText ? metadata : []}
          actions={
            fetched && audioText
              ? [
                  {
                    id: "copy",
                    label: "Copy",
                    kind: "copy",
                    onClick: () => copy(audioText, "Transcript copied to clipboard."),
                  },
                  {
                    id: "download",
                    label: "Download",
                    kind: "download",
                    onClick: () =>
                      download(
                        audioText,
                        `transcript_${Date.now()}.txt`,
                        { successDescription: "Transcript downloaded." }
                      ),
                  },
                ]
              : []
          }
          onClear={handleClearAudioInput}
        />
      }
    />
  );
};

export default ASRPage;
