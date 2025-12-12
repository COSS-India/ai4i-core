// TTS service testing page with text input, voice selection, and audio playback

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
  useToast,
  VStack,
} from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import Head from "next/head";
import React, { useState, useEffect } from "react";
import { FaRegFileAudio } from "react-icons/fa";
import ContentLayout from "../components/common/ContentLayout";
import LoadingSpinner from "../components/common/LoadingSpinner";
import TextInput from "../components/tts/TextInput";
import TTSResults from "../components/tts/TTSResults";
import VoiceSelector from "../components/tts/VoiceSelector";
import { useTTS } from "../hooks/useTTS";
import { listVoices, listTTSServices, getTTSLanguagesForService } from "../services/ttsService";

const TTSPage: React.FC = () => {
  const toast = useToast();
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

  // Fetch available services from Model Management
  const { data: services, isLoading: servicesLoading } = useQuery({
    queryKey: ["tts-services"],
    queryFn: listTTSServices,
    staleTime: 10 * 60 * 1000, // 10 minutes
  });

  // Clear serviceId if it doesn't exist in services list
  useEffect(() => {
    if (services && services.length > 0 && serviceId) {
      const serviceExists = services.some(s => s.service_id === serviceId);
      if (!serviceExists) {
        setServiceId("");
      }
    } else if (services && services.length === 0 && serviceId) {
      // Clear serviceId if no services available
      setServiceId("");
    }
  }, [services, serviceId]);

  // Check if we should fetch languages - only when services are loaded and service exists
  const shouldFetchLanguages = !servicesLoading && 
                                !!services && 
                                Array.isArray(services) &&
                                services.length > 0 && 
                                !!serviceId &&
                                services.some(s => s.service_id === serviceId);

  // Fetch available languages for selected service
  const { data: serviceLanguages, isLoading: languagesLoading, isFetching: languagesFetching } = useQuery({
    queryKey: ["tts-languages", serviceId, services?.length],
    queryFn: () => getTTSLanguagesForService(serviceId),
    enabled: shouldFetchLanguages, // Only fetch if all conditions are met
    retry: false, // Don't retry if service not found
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchOnWindowFocus: false, // Don't refetch on window focus
  });
  
  // Only show loading if query is actually enabled and fetching
  const isLanguagesActuallyLoading = shouldFetchLanguages && (languagesLoading || languagesFetching);

  // Check if we should fetch voices - only when service exists and is valid
  const shouldFetchVoices = !servicesLoading && 
                            !!services && 
                            Array.isArray(services) &&
                            services.length > 0 && 
                            !!serviceId &&
                            services.some(s => s.service_id === serviceId);

  // Fetch available voices (only when service is selected and valid)
  const { data: voicesData, isLoading: voicesLoading, isFetching: voicesFetching } = useQuery({
    queryKey: ["tts-voices", language, gender, serviceId, services?.length],
    queryFn: () => listVoices({ language, gender }),
    enabled: shouldFetchVoices, // Only fetch voices when service is valid
    retry: false,
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchOnWindowFocus: false,
  });
  
  // Only show loading if query is actually enabled and fetching
  const isVoicesActuallyLoading = shouldFetchVoices && (voicesLoading || voicesFetching);

  const handleGenerate = () => {
    if (!inputText.trim()) {
      toast({
        title: "Input Required",
        description: "Please enter text to synthesize.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    if (!serviceId) {
      toast({
        title: "Service Required",
        description: "Please select a TTS service.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    performInference(inputText);
  };

  // Get languages from selected service or empty array
  const availableLanguages = serviceLanguages?.supported_languages || [];
  
  // Get selected service details
  const selectedService = services?.find((s) => s.service_id === serviceId);

  return (
    <>
      <Head>
        <title>TTS - Text-to-Speech | AI4Inclusion Console</title>
        <meta
          name="description"
          content="Test Text-to-Speech with multiple voice options and audio formats"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={8} w="full">
          {/* Page Header */}
          <Box textAlign="center">
            <Heading size="xl" color="gray.800" mb={2}>
              Text-to-Speech
            </Heading>
            <Text color="gray.600" fontSize="lg">
              Convert text to natural-sounding speech with multiple voice
              options
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
                {/* Service Selection */}
                <Box>
                  <FormControl>
                    <FormLabel className="dview-service-try-option-title">
                      TTS Service:
                    </FormLabel>
                    {servicesLoading ? (
                      <Box textAlign="center" p={4}>
                        <LoadingSpinner label="Loading services..." />
                      </Box>
                    ) : (
                      <Select
                        placeholder="Select a TTS service"
                        value={serviceId}
                        onChange={(e) => setServiceId(e.target.value)}
                      >
                        {services?.map((service) => (
                          <option key={service.service_id} value={service.service_id}>
                            {service.name || service.service_id}
                          </option>
                        ))}
                      </Select>
                    )}
                  </FormControl>

                  <Text
                    className="dview-service-try-option-title"
                    mt={4}
                    mb={2}
                  >
                    Service Configuration
                  </Text>

                  {!serviceId ? (
                    <Box
                      p={3}
                      bg="gray.50"
                      borderRadius="md"
                      textAlign="center"
                    >
                      <Text fontSize="sm" color="gray.600">
                        No service selected
                      </Text>
                    </Box>
                  ) : selectedService ? (
                    <Box p={3} bg="gray.50" borderRadius="md">
                      <Text fontSize="sm" color="gray.600" mb={1}>
                        <strong>Provider:</strong> {selectedService.provider || "Unknown"}
                      </Text>
                      <Text fontSize="sm" color="gray.600" mb={1}>
                        <strong>Description:</strong> {selectedService.serviceDescription || selectedService.description || "No description"}
                      </Text>
                      <Text fontSize="sm" color="gray.600" mb={1}>
                        <strong>Supported Languages:</strong>{" "}
                        {languagesLoading ? "Loading..." : availableLanguages.length}
                      </Text>
                      <Text fontSize="sm" color="gray.600" mb={1}>
                        <strong>Service ID:</strong> {selectedService.service_id}
                      </Text>
                      {selectedService.triton_endpoint && (
                        <Text fontSize="sm" color="gray.600">
                          <strong>Endpoint:</strong> {selectedService.triton_endpoint}
                        </Text>
                      )}
                    </Box>
                  ) : (
                    <Box
                      p={3}
                      bg="yellow.50"
                      borderRadius="md"
                      textAlign="center"
                    >
                      <Text fontSize="sm" color="yellow.700">
                        Service not found
                      </Text>
                    </Box>
                  )}
                </Box>

                {/* Voice Selector */}
                <Box>
                  <Text className="dview-service-try-option-title" mb={4}>
                    Voice Configuration
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
                    availableLanguages={serviceId ? availableLanguages : []}
                    availableVoices={voicesData?.voices}
                    loading={isVoicesActuallyLoading || isLanguagesActuallyLoading}
                  />
                </Box>

                {/* Text Input */}
                <Box>
                  <TextInput
                    value={inputText}
                    onChange={setInputText}
                    language={language}
                    maxLength={512}
                    placeholder="Enter text to synthesize..."
                    disabled={fetching}
                  />
                </Box>

                {/* Generate Button */}
                <Button
                  leftIcon={<FaRegFileAudio />}
                  colorScheme="orange"
                  size="lg"
                  onClick={handleGenerate}
                  isLoading={fetching}
                  loadingText="Generating..."
                  isDisabled={!inputText.trim() || fetching}
                >
                  Generate Audio
                </Button>
              </VStack>
            </GridItem>

            {/* Results Panel */}
            <GridItem>
              <VStack spacing={6} align="stretch">
                {/* Progress Indicator */}
                {fetching && (
                  <Box>
                    <Text mb={2} fontSize="sm" color="gray.600">
                      Generating speech...
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

                {/* TTS Results */}
                {fetched && audio && (
                  <TTSResults
                    audioSrc={audio}
                    wordCount={requestWordCount}
                    responseTime={Number(requestTime)}
                    audioDuration={audioDuration}
                  />
                )}

                {/* Clear Results Button */}
                {fetched && (
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
                )}

                {/* Instructions */}
                {!fetched && !fetching && (
                  <Box p={6} bg="gray.50" borderRadius="md" textAlign="center">
                    <Text color="gray.600" fontSize="sm">
                      Enter text and click &quot;Generate Audio&quot; to create
                      speech synthesis. You can adjust voice settings and audio
                      format in the configuration panel.
                    </Text>
                  </Box>
                )}
              </VStack>
            </GridItem>
          </Grid>

          {/* Loading Indicators */}
          {(isVoicesActuallyLoading || servicesLoading || isLanguagesActuallyLoading) && (
            <Box textAlign="center">
              <LoadingSpinner 
                label={
                  servicesLoading 
                    ? "Loading services..." 
                    : isLanguagesActuallyLoading
                    ? "Loading languages..." 
                    : isVoicesActuallyLoading
                    ? "Loading voice options..."
                    : ""
                } 
              />
            </Box>
          )}
        </VStack>
      </ContentLayout>
    </>
  );
};

export default TTSPage;
