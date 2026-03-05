// ASR service testing page with recording, file upload, and results display

import {
  Box,
  Button,
  FormControl,
  FormLabel,
  Grid,
  GridItem,
  Heading,
  Progress,
  Select,
  Text,
  VStack,
} from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import Head from "next/head";
import React from "react";
import { FaFileAlt } from "react-icons/fa";
import ASRResults from "../components/asr/ASRResults";
import AudioRecorder from "../components/asr/AudioRecorder";
import ContentLayout from "../components/common/ContentLayout";
import LoadingSpinner from "../components/common/LoadingSpinner";
import { ASR_SUPPORTED_LANGUAGES } from "../config/constants";
import { getServiceDescription, getServiceTitle } from "../config/serviceMetadata";
import { useASR } from "../hooks/useASR";
import { listASRServices, ASRServiceDetails } from "../services/asrService";
import { useToastWithDeduplication } from "../hooks/useToastWithDeduplication";

const ASRPage: React.FC = () => {
  const toast = useToastWithDeduplication();
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
    pendingAudio,
    setPendingAudio,
    startRecording,
    stopRecording,
    runTranscribe,
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

  const handleRecordingChange = (isRecording: boolean) => {
    if (isRecording) {
      startRecording();
    } else {
      stopRecording();
    }
  };

  const handleAudioReady = (audioBase64: string) => {
    setPendingAudio(audioBase64);
  };

  const canTranscribe =
    !!pendingAudio && !!serviceId?.trim() && !!language?.trim() && !fetching;

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
            <Heading size="xl" color="gray.800" mb={2} userSelect="none" cursor="default" tabIndex={-1}>
              {getServiceTitle("asr")}
            </Heading>
            <Text color="gray.600" fontSize="lg" userSelect="none" cursor="default">
              {getServiceDescription("asr")}
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
            <GridItem pt={0} mt={0} alignSelf="flex-start">
              <VStack spacing={6} align="stretch" pt={0} mt={0}>
                {/* Inference Mode Selection */}
                <FormControl mt={0} pt={0}>
                  <FormLabel className="dview-service-try-option-title" mt={0}>
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
                    placeholder={servicesLoading ? "Loading..." : "Select"}
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
                  {serviceId && asrServices && (
                    <Box mt={2} p={3} bg="orange.50" borderRadius="md" border="1px" borderColor="orange.200">
                      {(() => {
                        const selectedService = asrServices.find((s) => s.service_id === serviceId);
                        return selectedService ? (
                          <>
                            <Text fontSize="sm" color="gray.700" mb={1}>
                              <strong>Service ID:</strong> {selectedService.service_id}
                            </Text>
                            <Text fontSize="sm" color="gray.700" mb={1}>
                              <strong>Name:</strong> {selectedService.name || selectedService.service_id}
                            </Text>
                            <Text fontSize="sm" color="gray.700" mb={1}>
                              <strong>Description:</strong> {selectedService.description || "No description available"}
                            </Text>
                          </>
                        ) : null;
                      })()}
                    </Box>
                  )}
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
                    placeholder="Select"
                  >
                    {ASR_SUPPORTED_LANGUAGES.map((lang) => (
                      <option key={lang.code} value={lang.code}>
                        {lang.label}
                      </option>
                    ))}
                  </Select>
                </FormControl>

                {/* Audio Input */}
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
                    disabled={fetching || !serviceId || !language}
                    timer={timer}
                  />
                </Box>

                {/* Instruction above Transcribe (same order as TTS: instruction then button) */}
                <Box p={3} borderRadius="md" borderWidth="1px" borderColor="gray.200" bg="gray.50">
                  <Text fontSize="sm" color="gray.600">
                    Record or upload audio above, then click Transcribe to generate the transcript.
                  </Text>
                </Box>

                {/* Transcribe Button - same UI order as TTS Generate Audio */}
                <Button
                  leftIcon={<FaFileAlt />}
                  colorScheme="orange"
                  size="lg"
                  onClick={runTranscribe}
                  isLoading={fetching}
                  loadingText="Transcribing..."
                  isDisabled={!canTranscribe}
                >
                  Transcribe
                </Button>
              </VStack>
            </GridItem>

            {/* Results Panel */}
            <GridItem pt={0} mt={0} alignSelf="flex-start">
              <VStack spacing={6} align="stretch" pt={0} mt={0}>
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
        </VStack>
      </ContentLayout>
    </>
  );
};

export default ASRPage;
