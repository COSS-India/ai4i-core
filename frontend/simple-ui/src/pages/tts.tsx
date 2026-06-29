// TTS service testing page — reusable service page architecture

import { Box, Text } from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import React, { useMemo, useState } from "react";
import { FaRegFileAudio } from "react-icons/fa";
import TTSResults from "../components/tts/TTSResults";
import VoiceSelector from "../components/tts/VoiceSelector";
import {
  mapToServiceOptions,
  RequestContainer,
  ResponseContainer,
  ServicePageLayout,
} from "../components/service-page";
import { getServicePageDefaults } from '../constants/servicePageConfig';
import { useTTS } from "../hooks/useTTS";
import { listVoices, listTTSServices } from "../services/ttsService";

const pageDefaults = getServicePageDefaults("tts");
const indoAryanLanguages = ["hi", "mr", "as", "bn", "gu", "or", "pa"];

const TTSPage: React.FC = () => {
  const [serviceId, setServiceId] = useState<string>("");
  const {
    language,
    gender,
    audioFormat,
    samplingRate,
    inputText,
    audio,
    fetching,
    fetched,
    requestWordCount,
    requestTime,
    audioDuration,
    error,
    performInference,
    setInputText,
    setLanguage,
    setGender,
    setAudioFormat,
    setSamplingRate,
    clearResults,
  } = useTTS(serviceId);

  const { data: ttsServices, isLoading: servicesLoading } = useQuery({
    queryKey: ["tts-services"],
    queryFn: listTTSServices,
    staleTime: 10 * 60 * 1000,
  });

  const { data: voicesData, isLoading: voicesLoading } = useQuery({
    queryKey: ["tts-voices", language, gender],
    queryFn: () => listVoices({ language, gender: gender as "male" | "female" }),
    staleTime: 5 * 60 * 1000,
    retry: false,
    enabled: !!language?.trim() && (gender === "male" || gender === "female"),
  });

  const serviceOptions = useMemo(
    () => mapToServiceOptions(ttsServices ?? []),
    [ttsServices]
  );

  const allMandatoryFilled =
    !!serviceId?.trim() &&
    !!language?.trim() &&
    !!gender &&
    (gender === "male" || gender === "female") &&
    !!audioFormat?.trim() &&
    !!inputText?.trim();

  return (
    <ServicePageLayout
      serviceId="tts"
      headDescription="Generate natural-sounding speech from text in Indic languages"
      requestPanel={
        <RequestContainer
          serviceDropdown={{
            label: "TTS Service",
            value: serviceId,
            onChange: setServiceId,
            options: serviceOptions,
            loading: servicesLoading,
            disabled: fetching,
          }}
          inputType="text"
          textInput={{
            value: inputText,
            onChange: setInputText,
            maxLength: pageDefaults.maxTextLength,
            placeholder: pageDefaults.textPlaceholder,
            label: "Text Input",
            disabled: fetching || !serviceId,
          }}
          helperText={pageDefaults.helperText}
          submitButton={{
            label: pageDefaults.submitLabel,
            loadingLabel: pageDefaults.submitLoadingLabel,
            onClick: () => allMandatoryFilled && performInference(inputText),
            isLoading: fetching,
            isDisabled: !allMandatoryFilled || fetching,
            icon: <FaRegFileAudio />,
          }}
        >
          <Box>
            <Text className="dview-service-try-option-title" mb={4} fontSize="sm" fontWeight="semibold">
              Audio Configuration
            </Text>
            <VoiceSelector
              language={language}
              gender={gender}
              audioFormat={audioFormat}
              samplingRate={samplingRate}
              onLanguageChange={setLanguage}
              onGenderChange={setGender}
              onFormatChange={setAudioFormat}
              onSampleRateChange={setSamplingRate}
              availableLanguages={serviceId ? indoAryanLanguages : []}
              availableVoices={voicesData?.voices ?? []}
              loading={voicesLoading}
              disabled={fetching || !serviceId}
            />
          </Box>
        </RequestContainer>
      }
      responsePanel={
        <ResponseContainer
          fetching={fetching}
          fetchingLabel="Generating speech..."
          error={error}
          fetched={fetched}
          hasResult={!!audio}
          result={
            fetched && audio ? (
              <TTSResults
                audioSrc={audio}
                audioFormat={audioFormat}
                wordCount={requestWordCount}
                responseTime={Number(requestTime)}
                audioDuration={audioDuration}
                captionText={inputText}
                captionLang={language}
              />
            ) : undefined
          }
          onClear={clearResults}
        />
      }
    />
  );
};

export default TTSPage;
