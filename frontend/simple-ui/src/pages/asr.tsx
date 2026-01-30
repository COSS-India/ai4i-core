// ASR service testing page with recording, file upload, and results display

import {
  Box,
  FormControl,
  FormLabel,
  Grid,
  GridItem,
  Heading,
  Progress,
  Select,
  Text,
  useToast,
  VStack,
} from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import Head from "next/head";
import React from "react";
import ASRResults from "../components/asr/ASRResults";
import AudioRecorder from "../components/asr/AudioRecorder";
import ContentLayout from "../components/common/ContentLayout";
import LoadingSpinner from "../components/common/LoadingSpinner";
import { ASR_SUPPORTED_LANGUAGES } from "../config/constants";
import { useASR } from "../hooks/useASR";
import { listASRServices, ASRServiceDetails } from "../services/asrService";

const ASRPage: React.FC = () => {
  const toast = useToast();
  const {
    language,
    sampleRate,
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
    startRecording,
    stopRecording,
    performInference,
    setLanguage,
    setSampleRate,
    setServiceId,
    setInferenceMode,
    clearResults,
  } = useASR();

  // Fetch available ASR services from model management
  const { data: asrServices, isLoading: servicesLoading } = useQuery<ASRServiceDetails[]>({
    queryKey: ["asr-services"],
    queryFn: listASRServices,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  // Auto-select first available ASR service when list loads
  React.useEffect(() => {
    if (!asrServices || asrServices.length === 0) return;
    if (!serviceId || serviceId === "asr_am_ensemble") {
      // If no service selected or still using default, select first available
      setServiceId(asrServices[0].service_id);
    }
  }, [asrServices, serviceId, setServiceId]);

  const handleRecordingChange = (isRecording: boolean) => {
    if (isRecording) {
      startRecording();
    } else {
      stopRecording();
    }
  };

  const handleAudioReady = (audioBase64: string) => {
    // Process the audio using the useASR hook
    console.log(
      "handleAudioReady called with audioBase64 length:",
      audioBase64.length
    );
    console.log("Audio ready for processing, calling performInference...");
    performInference(audioBase64);
  };

  return (
    <>
      <Head>
        <title>ASR - Speech Recognition | AI4Inclusion Console</title>
        <meta
          name="description"
          content="Test Automatic Speech Recognition with microphone recording and file upload"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={8} w="full">
          {/* Page Header */}
          <Box textAlign="center">
            <Heading size="xl" color="gray.800" mb={2}>
              Automatic Speech Recognition
            </Heading>
            <Text color="gray.600" fontSize="lg">
              Convert speech to text with support for 12+ Indic languages
            </Text>
          </Box>

          <Grid
            templateColumns={{ base: "1fr", lg: "1fr 1fr" }}
            gap={8}
            w="full"
            maxW="1200px"
            mx="auto"
          >
            {/* Configuration Panel */}
            <GridItem>
              <VStack spacing={6} align="stretch">
                {/* Inference Mode Selection */}
                <FormControl>
                  <FormLabel className="dview-service-try-option-title">
                    Inference Mode
                  </FormLabel>
                  <Select
                    value={inferenceMode}
                    onChange={(e) =>
                      setInferenceMode(e.target.value as "rest" | "streaming")
                    }
                  >
                    <option value="rest">REST API</option>
                    <option value="streaming">WebSocket Streaming</option>
                  </Select>
                </FormControl>

                {/* ASR Service Selection */}
                <FormControl>
                  <FormLabel className="dview-service-try-option-title">
                    ASR Service{" "}
                    <Text as="span" color="red.500">
                      *
                    </Text>
                  </FormLabel>
                  <Select
                    value={serviceId}
                    onChange={(e) => setServiceId(e.target.value)}
                    isDisabled={fetching || servicesLoading}
                    placeholder={servicesLoading ? "Loading services..." : "Select an ASR service"}
                  >
                    {asrServices?.map((service) => {
                      const version = service.modelVersion || service.model_version;
                      const displayText = version ? `${service.service_id} (${version})` : service.service_id;
                      return (
                        <option key={service.service_id} value={service.service_id}>
                          {displayText}
                        </option>
                      );
                    })}
                  </Select>
                </FormControl>

                {/* Language Selection */}
                <FormControl>
                  <FormLabel className="dview-service-try-option-title">
                    Language{" "}
                    <Text as="span" color="red.500">
                      *
                    </Text>
                  </FormLabel>
                  <Select
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                  >
                    {ASR_SUPPORTED_LANGUAGES.map((lang) => (
                      <option key={lang.code} value={lang.code}>
                        {lang.label}
                      </option>
                    ))}
                  </Select>
                </FormControl>

                {/* Audio Recorder */}
                <Box>
                  <FormLabel className="dview-service-try-option-title" mb={4}>
                    Audio Input{" "}
                    <Text as="span" color="red.500">
                      *
                    </Text>
                  </FormLabel>
                  <AudioRecorder
                    onAudioReady={handleAudioReady}
                    isRecording={recording}
                    onRecordingChange={handleRecordingChange}
                    sampleRate={sampleRate}
                    disabled={fetching}
                    timer={timer}
                  />
                </Box>
              </VStack>
            </GridItem>

            {/* Results Panel */}
            <GridItem>
              <VStack spacing={6} align="stretch">
                {/* Progress Indicator */}
                {fetching && (
                  <Box>
                    <Text mb={2} fontSize="sm" color="gray.600">
                      Processing audio...
                    </Text>
                    <Progress size="xs" isIndeterminate colorScheme="orange" />
                  </Box>
                )}

                {/* Error Display */}
                {error && (
                  <Box
                    p={4}
                    bg="red.50"
                    borderRadius="md"
                    border="1px"
                    borderColor="red.200"
                  >
                    <Text color="red.600" fontSize="sm">
                      {error}
                    </Text>
                  </Box>
                )}

                {/* ASR Results */}
                {fetched && audioText && (
                  <>
                    <ASRResults
                      transcript={audioText}
                      responseWordCount={responseWordCount}
                      responseTime={Number(requestTime)}
                    />

                    {/* Clear Results Button */}
                    <Box textAlign="center">
                      <button
                        onClick={clearResults}
                        style={{
                          padding: "8px 16px",
                          backgroundColor: "#f7fafc",
                          border: "1px solid #e2e8f0",
                          borderRadius: "6px",
                          cursor: "pointer",
                          fontSize: "14px",
                          color: "#4a5568",
                        }}
                      >
                        Clear Results
                      </button>
                    </Box>
                  </>
                )}
              </VStack>
            </GridItem>
          </Grid>

          {/* Services Loading Indicator */}
          {servicesLoading && (
            <Box textAlign="center">
              <LoadingSpinner label="Loading ASR services..." />
            </Box>
          )}
        </VStack>
      </ContentLayout>
    </>
  );
};

export default ASRPage;
