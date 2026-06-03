// Audio Language Detection — reusable service page architecture

import { Box, HStack, Text, VStack } from "@chakra-ui/react";
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
import { AUDIO_LANGUAGE_DETECTION_ERRORS } from "../config/constants";
import { getServicePageDefaults } from "../config/servicePageConfig";
import {
  performAudioLanguageDetectionInference,
  listAudioLanguageDetectionServices,
} from "../services/audioLanguageDetectionService";
import { parseAudioLanguageDetectionOutput } from "../types/inference";
import { useAudioRecorder } from "../hooks/useAudioRecorder";
import { extractErrorInfo } from "../utils/errorHandler";
import { useToastWithDeduplication } from "../hooks/useToastWithDeduplication";

const pageDefaults = getServicePageDefaults("audio-language-detection");

const AudioLanguageDetectionPage: React.FC = () => {
  const toast = useToastWithDeduplication();
  const [audioData, setAudioData] = useState<string | null>(null);
  const [audioClearToken, setAudioClearToken] = useState(0);
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [result, setResult] = useState<unknown>(null);
  const [responseTime, setResponseTime] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [selectedServiceId, setSelectedServiceId] = useState<string>("");

  const { data: services = [], isLoading: isLoadingServices, isError: servicesError } = useQuery({
    queryKey: ["audioLanguageDetectionServices"],
    queryFn: listAudioLanguageDetectionServices,
    staleTime: 5 * 60 * 1000,
  });

  const serviceOptions = useMemo(() => mapToServiceOptions(services), [services]);

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
      const err = AUDIO_LANGUAGE_DETECTION_ERRORS.FILE_REQUIRED;
      toast({ title: err.title, description: err.description, status: "error", duration: 3000, isClosable: true });
      return;
    }
    if (!selectedServiceId) {
      toast({ title: "No Service Selected", description: "Please select a service.", status: "warning", duration: 3000, isClosable: true });
      return;
    }

    setFetching(true);
    setError(null);
    setFetched(false);
    try {
      const startTime = Date.now();
      const response = await performAudioLanguageDetectionInference(audioData, selectedServiceId);
      setResult(response.data);
      setResponseTime((Date.now() - startTime) / 1000);
      setFetched(true);
    } catch (err: unknown) {
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(err, "audio-language-detection");
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

  const outputItem =
    result && typeof result === "object" && result !== null && "output" in result
      ? (result as { output?: unknown[] }).output?.[0]
      : result;
  const { language, confidence: conf } = parseAudioLanguageDetectionOutput(
    outputItem as Parameters<typeof parseAudioLanguageDetectionOutput>[0]
  );

  return (
    <ServicePageLayout
      serviceId="audio-language-detection"
      requestPanel={
        <RequestContainer
          serviceDropdown={{
            label: "Audio Language Detection Service",
            value: selectedServiceId,
            onChange: setSelectedServiceId,
            options: serviceOptions,
            loading: isLoadingServices,
            disabled: fetching,
            error: servicesError ? "Failed to load services. Please refresh the page." : null,
          }}
          inputType="audio"
          audioInput={{
            children: (
              <AudioInputSection
                audioData={audioData}
                isRecording={isRecording}
                onAudioReady={handleAudioReady}
                onRecordingChange={handleRecordingChange}
                disabled={fetching || !selectedServiceId}
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
            isDisabled: !audioData || !selectedServiceId || fetching,
          }}
        />
      }
      responsePanel={
        <ResponseContainer
          fetching={fetching}
          fetchingLabel="Processing audio..."
          error={error}
          fetched={fetched}
          hasResult={fetched && !!result}
          metadata={fetched ? buildResponseMetadata({ responseTimeMs: responseTime * 1000 }) : []}
          result={
            fetched && result ? (
              <Box p={4} bg="gray.50" borderRadius="md" border="1px" borderColor="gray.200">
                <Text fontSize="sm" fontWeight="semibold" mb={3} color="gray.700">
                  Audio Language Detection Results:
                </Text>
                <Box p={4} bg="white" borderRadius="md" border="2px solid" borderColor="orange.300">
                  <VStack align="start" spacing={3}>
                    <Box>
                      <Text fontSize="xs" color="gray.600" mb={1}>
                        Detected Language
                      </Text>
                      <Text fontSize="2xl" fontWeight="bold" color="orange.700">
                        {language}
                      </Text>
                    </Box>
                    {conf !== null && (
                      <Box w="full">
                        <Text fontSize="xs" color="gray.600" mb={1}>
                          Confidence Score
                        </Text>
                        <HStack spacing={2} align="center" w="full">
                          <Text fontSize="lg" fontWeight="semibold" color="gray.800">
                            {(conf * 100).toFixed(2)}%
                          </Text>
                          <Box flex={1} h="8px" bg="gray.200" borderRadius="full" overflow="hidden">
                            <Box h="100%" bg="orange.500" w={`${conf * 100}%`} transition="width 0.3s" />
                          </Box>
                        </HStack>
                      </Box>
                    )}
                  </VStack>
                </Box>
              </Box>
            ) : undefined
          }
          onClear={handleClearAudioInput}
        />
      }
    />
  );
};

export default AudioLanguageDetectionPage;
