// Pipeline service page for Speech-to-Speech translation

import {
  Alert,
  AlertDescription,
  AlertIcon,
  Box,
  Button,
  FormControl,
  FormLabel,
  Grid,
  GridItem,
  Heading,
  Progress,
  Select,
  SimpleGrid,
  Stat,
  StatHelpText,
  StatLabel,
  StatNumber,
  Text,
  Textarea,
  useToast,
  VStack,
  HStack,
  Flex,
} from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import Head from "next/head";
import { useRouter } from "next/router";
import React, { useState } from "react";
import { FaMicrophone, FaMicrophoneSlash } from "react-icons/fa";
import ContentLayout from "../components/common/ContentLayout";
import {
  ASR_SUPPORTED_LANGUAGES,
  formatDuration,
  MAX_RECORDING_DURATION,
  TTS_SUPPORTED_LANGUAGES,
} from "../config/constants";
import { usePipeline } from "../hooks/usePipeline";
import { listASRServices, ASRServiceDetails } from "../services/asrService";
import { listNMTServices } from "../services/nmtService";
import { listTTSServices, TTSServiceDetailsResponse } from "../services/ttsService";

const PipelinePage: React.FC = () => {
  const toast = useToast();
  const router = useRouter();
  const [sourceLanguage, setSourceLanguage] = useState("hi");
  const [targetLanguage, setTargetLanguage] = useState("mr");
  const [asrServiceId, setAsrServiceId] = useState<string>("");
  const [nmtServiceId, setNmtServiceId] = useState<string>("");
  const [ttsServiceId, setTtsServiceId] = useState<string>("");

  const {
    isLoading,
    result,
    isRecording,
    timer,
    startRecording,
    stopRecording,
    processRecordedAudio,
    processUploadedAudio,
    setProcessRecordedAudioCallback,
  } = usePipeline();

  // Fetch available services
  const { data: asrServices } = useQuery<ASRServiceDetails[]>({
    queryKey: ["asr-services"],
    queryFn: listASRServices,
    staleTime: 5 * 60 * 1000,
  });

  const { data: nmtServices } = useQuery({
    queryKey: ["nmt-services"],
    queryFn: listNMTServices,
    staleTime: 5 * 60 * 1000,
  });

  const { data: ttsServices } = useQuery<TTSServiceDetailsResponse[]>({
    queryKey: ["tts-services"],
    queryFn: listTTSServices,
    staleTime: 5 * 60 * 1000,
  });

  // Auto-select first available ASR service when list loads
  React.useEffect(() => {
    if (!asrServices || asrServices.length === 0) return;
    if (!asrServiceId) {
      setAsrServiceId(asrServices[0].service_id);
    }
  }, [asrServices, asrServiceId]);

  // Auto-select first available NMT service when list loads
  React.useEffect(() => {
    if (!nmtServices || nmtServices.length === 0) return;
    if (!nmtServiceId) {
      setNmtServiceId(nmtServices[0].service_id);
    }
  }, [nmtServices, nmtServiceId]);

  // Auto-select first available TTS service when list loads
  React.useEffect(() => {
    if (!ttsServices || ttsServices.length === 0) return;
    if (!ttsServiceId) {
      setTtsServiceId(ttsServices[0].service_id);
    }
  }, [ttsServices, ttsServiceId]);

  const handleRecordClick = async () => {
    if (isRecording) {
      stopRecording();
    } else {
      // Set the callback with current config before starting recording
      setProcessRecordedAudioCallback(
        sourceLanguage,
        targetLanguage,
        asrServiceId,
        nmtServiceId,
        ttsServiceId
      );
      startRecording();
    }
  };

  const handleFileUpload = async (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      await processUploadedAudio(
        file,
        sourceLanguage,
        targetLanguage,
        asrServiceId,
        nmtServiceId,
        ttsServiceId
      );
    } catch (error) {
      console.error("Pipeline upload error:", error);
    }

    // Reset file input
    event.target.value = "";
  };

  // Get word count helper
  const getWordCount = (text: string): number => {
    return text.trim().split(/\s+/).filter(Boolean).length;
  };

  return (
    <>
      <Head>
        <title>Speech to Speech | AI4Inclusion Console</title>
        <meta
          name="description"
          content="Speech-to-Speech translation pipeline combining ASR, NMT, and TTS"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={8} w="full">
          {/* Page Header */}
          <Box w="full" maxW="1200px" mx="auto">
            <Flex
              direction="row"
              justify="space-between"
              align="center"
              mb={4}
              w="full"
            >
              <Box flex={1} textAlign="center">
                <Heading size="lg" color="gray.800" mb={1} userSelect="none" cursor="default" tabIndex={-1}>
                  Speech to Speech
                </Heading>
                <Text color="gray.600" fontSize="sm" userSelect="none" cursor="default">
                  Chain Speech, Translation, and Voice models for end-to-end speech
                  conversion.
                </Text>
              </Box>
              <Button
                size="sm"
                variant="outline"
                colorScheme="orange"
                onClick={() => router.push("/pipeline-builder")}
                ml={4}
              >
                Customize Pipeline
              </Button>
            </Flex>

            {/* Info Alert */}
            <Alert status="info" borderRadius="md" alignItems="center">
              <AlertIcon />
              <AlertDescription>
                The pipeline chains Automatic Speech Recognition (ASR), Neural
                Machine Translation (NMT), and Text-to-Speech (TTS) services to
                convert speech from one language to another.
              </AlertDescription>
            </Alert>
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
                {/* Source Language */}
                <FormControl>
                  <FormLabel className="dview-service-try-option-title">
                    Source Language
                  </FormLabel>
                  <Select
                    value={sourceLanguage}
                    onChange={(e) => setSourceLanguage(e.target.value)}
                  >
                    {ASR_SUPPORTED_LANGUAGES.map((lang) => (
                      <option key={lang.code} value={lang.code}>
                        {lang.label}
                      </option>
                    ))}
                  </Select>
                </FormControl>

                {/* Target Language */}
                <FormControl>
                  <FormLabel className="dview-service-try-option-title">
                    Target Language
                  </FormLabel>
                  <Select
                    value={targetLanguage}
                    onChange={(e) => setTargetLanguage(e.target.value)}
                  >
                    {TTS_SUPPORTED_LANGUAGES.map((lang) => (
                      <option key={lang.code} value={lang.code}>
                        {lang.label}
                      </option>
                    ))}
                  </Select>
                </FormControl>

                {/* ASR Service */}
                <FormControl>
                  <FormLabel className="dview-service-try-option-title">
                    ASR Service
                  </FormLabel>
                  <Select
                    value={asrServiceId}
                    onChange={(e) => setAsrServiceId(e.target.value)}
                    placeholder="Select a ASR service"
                  >
                    {asrServices?.map((service) => (
                      <option key={service.service_id} value={service.service_id}>
                        {service.name || service.service_id} {service.model_version ? `(${service.model_version})` : ''}
                      </option>
                    ))}
                  </Select>
                  {asrServiceId && asrServices && (
                    <Box mt={2} p={3} bg="orange.50" borderRadius="md" border="1px" borderColor="orange.200">
                      {(() => {
                        const selectedService = asrServices.find((s) => s.service_id === asrServiceId);
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

                {/* NMT Service */}
                <FormControl>
                  <FormLabel className="dview-service-try-option-title">
                    NMT Service
                  </FormLabel>
                  <Select
                    value={nmtServiceId}
                    onChange={(e) => setNmtServiceId(e.target.value)}
                    placeholder="Select a NMT service"
                  >
                    {nmtServices
                      ?.filter(
                        (service) =>
                          !service.service_id.toLowerCase().includes("facebook")
                      )
                      .map((service) => (
                        <option
                          key={service.service_id}
                          value={service.service_id}
                        >
                          {service.name || service.service_id} {service.model_version ? `(${service.model_version})` : ''}
                        </option>
                      ))}
                  </Select>
                  {nmtServiceId && nmtServices && (
                    <Box mt={2} p={3} bg="orange.50" borderRadius="md" border="1px" borderColor="orange.200">
                      {(() => {
                        const selectedService = nmtServices.find((s) => s.service_id === nmtServiceId);
                        return selectedService ? (
                          <>
                            <Text fontSize="sm" color="gray.700" mb={1}>
                              <strong>Service ID:</strong> {selectedService.service_id}
                            </Text>
                            <Text fontSize="sm" color="gray.700" mb={1}>
                              <strong>Name:</strong> {selectedService.name || selectedService.service_id}
                            </Text>
                            <Text fontSize="sm" color="gray.700" mb={1}>
                              <strong>Description:</strong> {selectedService.serviceDescription || selectedService.description || "No description available"}
                            </Text>
                          </>
                        ) : null;
                      })()}
                    </Box>
                  )}
                </FormControl>

                {/* TTS Service */}
                <FormControl>
                  <FormLabel className="dview-service-try-option-title">
                    TTS Service
                  </FormLabel>
                  <Select
                    value={ttsServiceId}
                    onChange={(e) => setTtsServiceId(e.target.value)}
                    placeholder="Select a TTS service"
                  >
                    {ttsServices?.map((service) => (
                      <option key={service.service_id} value={service.service_id}>
                        {service.name || service.service_id} {service.model_version ? `(${service.model_version})` : ''}
                      </option>
                    ))}
                  </Select>
                  {ttsServiceId && ttsServices && (
                    <Box mt={2} p={3} bg="orange.50" borderRadius="md" border="1px" borderColor="orange.200">
                      {(() => {
                        const selectedService = ttsServices.find((s) => s.service_id === ttsServiceId);
                        return selectedService ? (
                          <>
                            <Text fontSize="sm" color="gray.700" mb={1}>
                              <strong>Service ID:</strong> {selectedService.service_id}
                            </Text>
                            <Text fontSize="sm" color="gray.700" mb={1}>
                              <strong>Name:</strong> {selectedService.name || selectedService.service_id}
                            </Text>
                            <Text fontSize="sm" color="gray.700" mb={1}>
                              <strong>Description:</strong> {selectedService.serviceDescription || "No description available"}
                            </Text>
                          </>
                        ) : null;
                      })()}
                    </Box>
                  )}
                </FormControl>

                {/* Recording Timer Display */}
                {isRecording && (
                  <Alert status="info" borderRadius="md">
                    <AlertIcon />
                    <AlertDescription>
                      Recording Time: {formatDuration(timer)} /{" "}
                      {formatDuration(MAX_RECORDING_DURATION)} seconds
                    </AlertDescription>
                  </Alert>
                )}

                {/* Recording Button */}
                <Button
                  leftIcon={
                    isRecording ? <FaMicrophoneSlash /> : <FaMicrophone />
                  }
                  colorScheme={isRecording ? "red" : "orange"}
                  variant={isRecording ? "solid" : "outline"}
                  onClick={handleRecordClick}
                  disabled={isLoading}
                  w="full"
                  h="50px"
                >
                  {isRecording ? "Stop" : "Record"}
                </Button>

                {/* File Upload */}
                <Button
                  as="label"
                  cursor="pointer"
                  disabled={isLoading || isRecording}
                >
                  Upload
                  <input
                    type="file"
                    accept="audio/*"
                    onChange={handleFileUpload}
                    style={{ display: "none" }}
                  />
                </Button>
              </VStack>
            </GridItem>

            {/* Results Panel */}
            <GridItem>
              <VStack spacing={6} align="stretch">
                {/* Progress Indicator */}
                {isLoading && (
                  <Box>
                    <Text mb={2} fontSize="sm" color="gray.600">
                      Processing pipeline...
                    </Text>
                    <Progress size="xs" isIndeterminate colorScheme="orange" />
                  </Box>
                )}

                {/* Results Stats */}
                {result && (
                  <SimpleGrid
                    p={4}
                    bg="orange.50"
                    borderRadius="md"
                    border="1px"
                    borderColor="orange.200"
                    columns={2}
                    spacingX="20px"
                    spacingY="10px"
                  >
                    <Stat>
                      <StatLabel>Source Text</StatLabel>
                      <StatNumber>{getWordCount(result.sourceText)}</StatNumber>
                      <StatHelpText>words</StatHelpText>
                    </Stat>
                    <Stat>
                      <StatLabel>Translated Text</StatLabel>
                      <StatNumber>{getWordCount(result.targetText)}</StatNumber>
                      <StatHelpText>words</StatHelpText>
                    </Stat>
                  </SimpleGrid>
                )}

                {/* Source Text */}
                <Box>
                  <FormLabel
                    mb={2}
                    fontSize="sm"
                    fontWeight="semibold"
                    color="gray.700"
                  >
                    Transcribed Text (Source)
                  </FormLabel>
                  <Textarea
                    readOnly
                    value={result?.sourceText || ""}
                    placeholder="Transcribed text will appear here..."
                    rows={4}
                  />
                </Box>

                {/* Target Text */}
                <Box>
                  <FormLabel
                    mb={2}
                    fontSize="sm"
                    fontWeight="semibold"
                    color="gray.700"
                  >
                    Translated Text (Target)
                  </FormLabel>
                  <Textarea
                    readOnly
                    value={result?.targetText || ""}
                    placeholder="Translated text will appear here..."
                    rows={4}
                  />
                </Box>

                {/* Audio Player */}
                {result?.audio && (
                  <Box>
                    <FormLabel
                      mb={2}
                      fontSize="sm"
                      fontWeight="semibold"
                      color="gray.700"
                    >
                      Synthesized Audio (Target)
                    </FormLabel>
                    <audio
                      controls
                      src={result.audio}
                      style={{ width: "100%" }}
                    />
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

export default PipelinePage;
