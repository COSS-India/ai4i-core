// TTS service testing page with text input, voice selection, and audio playback

import {
  Box,
  Button,
  FormControl,
  FormLabel,
  Grid,
  GridItem,
  Heading,
  HStack,
  Progress,
  Select,
  Spinner,
  Text,
  useToast,
  VStack,
} from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import Head from "next/head";
import React, { useState } from "react";
import { FaRegFileAudio } from "react-icons/fa";
import ContentLayout from "../components/common/ContentLayout";
import LoadingSpinner from "../components/common/LoadingSpinner";
import { getServiceDescription, getServiceTitle } from "../config/serviceMetadata";
import TextInput from "../components/tts/TextInput";
import TTSResults from "../components/tts/TTSResults";
import VoiceSelector from "../components/tts/VoiceSelector";
import { useTTS } from "../hooks/useTTS";
import { listVoices, listTTSServices } from "../services/ttsService";
import { useToastWithDeduplication } from "../hooks/useToastWithDeduplication";

const TTSPage: React.FC = () => {
  const toast = useToastWithDeduplication();
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

  // Fetch available TTS services
  const { data: ttsServices, isLoading: servicesLoading } = useQuery({
    queryKey: ["tts-services"],
    queryFn: listTTSServices,
    staleTime: 10 * 60 * 1000, // 10 minutes
  });

  // Fetch available voices when language and voice are selected (short timeout + no retry)
  const { data: voicesData, isLoading: voicesLoading, isError: voicesError } = useQuery({
    queryKey: ["tts-voices", language, gender],
    queryFn: () => listVoices({ language, gender: gender as "male" | "female" }),
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: false,
    enabled: !!language?.trim() && (gender === "male" || gender === "female"),
  });

  const allMandatoryFilled =
    !!serviceId?.trim() &&
    !!language?.trim() &&
    !!gender &&
    (gender === "male" || gender === "female") &&
    !!audioFormat?.trim() &&
    !!inputText?.trim();

  const handleGenerate = () => {
    if (!allMandatoryFilled) return;
    performInference(inputText);
  };

  // Restrict available languages to Indo-Aryan list requested
  const indoAryanLanguages = ["hi", "mr", "as", "bn", "gu", "or", "pa"];

  return (
    <>
      <Head>
        <title>TTS - Text-to-Speech | AI4Inclusion Console</title>
        <meta
          name="description"
          content="Generate natural-sounding speech from text in Indic languages"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={8} w="full">
          {/* Page Header */}
          <Box textAlign="center">
            <Heading size="xl" color="gray.800" mb={2} userSelect="none" cursor="default" tabIndex={-1}>
              {getServiceTitle("tts")}
            </Heading>
            <Text color="gray.600" fontSize="lg" userSelect="none" cursor="default">
              {getServiceDescription("tts")}
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
                {/* Service Selection */}
                <FormControl mt={0} pt={0}>
                  <FormLabel fontSize="sm" fontWeight="semibold" mt={0}>
                    TTS Service{" "}
                    <Text as="span" color="red.500">*</Text>
                  </FormLabel>
                  {servicesLoading ? (
                    <HStack spacing={2} p={2}>
                      <Spinner size="sm" color="orange.500" />
                      <Text fontSize="sm" color="gray.600">Loading services...</Text>
                    </HStack>
                  ) : (
                    <Select
                      value={serviceId}
                      onChange={(e) => setServiceId(e.target.value)}
                      placeholder={servicesLoading ? "Loading..." : "Select"}
                      disabled={fetching}
                      size="md"
                      borderColor="gray.300"
                      _focus={{
                        borderColor: "orange.400",
                        boxShadow: "0 0 0 1px var(--chakra-colors-orange-400)",
                      }}
                    >
                      {ttsServices?.map((service) => (
                        <option key={service.service_id} value={service.service_id}>
                          {service.name || service.service_id} {service.model_version ? `(${service.model_version})` : ''}
                        </option>
                      ))}
                    </Select>
                  )}
                  {serviceId && ttsServices && (
                    <Box
                      mt={2}
                      p={3}
                      bg="orange.50"
                      borderRadius="md"
                      border="1px"
                      borderColor="orange.200"
                    >
                      {(() => {
                        const selectedService = ttsServices.find((s) => s.service_id === serviceId);
                        return selectedService ? (
                          <>
                            <Text fontSize="sm" color="gray.700" mb={1}>
                              <strong>Service Name:</strong>{" "}
                              {selectedService.name || selectedService.service_id}
                            </Text>
                            <Text fontSize="sm" color="gray.700" mb={1}>
                              <strong>Service Description:</strong>{" "}
                              {selectedService.serviceDescription || "No description available"}
                            </Text>
                          </>
                        ) : null;
                      })()}
                    </Box>
                  )}
                </FormControl>

                {/* Audio Configuration */}
                <Box>
                  <Text className="dview-service-try-option-title" mb={4}>
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

                {/* Instruction above Generate Audio */}
                <Text fontSize="sm" color="gray.600">
                  Enter text and click &quot;Generate Audio&quot; to create speech synthesis. You can adjust voice settings and audio format in the configuration panel.
                </Text>

                {/* Generate Button */}
                <Button
                  leftIcon={<FaRegFileAudio />}
                  colorScheme="orange"
                  size="lg"
                  onClick={handleGenerate}
                  isLoading={fetching}
                  loadingText="Generating..."
                  isDisabled={!allMandatoryFilled || fetching}
                >
                  Generate Audio
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
                    audioFormat={audioFormat}
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

              </VStack>
            </GridItem>
          </Grid>
        </VStack>
      </ContentLayout>
    </>
  );
};

export default TTSPage;
