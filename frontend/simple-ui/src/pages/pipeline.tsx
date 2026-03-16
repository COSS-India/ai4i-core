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
  VStack,
  HStack,
  Flex,
} from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import Head from "next/head";
import { useRouter } from "next/router";
import React, { useState } from "react";
import { FaMicrophone, FaMicrophoneSlash, FaUpload } from "react-icons/fa";
import ContentLayout from "../components/common/ContentLayout";
import {
  ASR_SUPPORTED_LANGUAGES,
  formatDuration,
  MAX_RECORDING_DURATION,
  TTS_SUPPORTED_LANGUAGES,
} from "../config/constants";
import { getServiceDescription, getServiceTitle } from "../config/serviceMetadata";
import { useAuth } from "../hooks/useAuth";
import { usePipeline } from "../hooks/usePipeline";
import { listASRServices, ASRServiceDetails } from "../services/asrService";
import { listNMTServices } from "../services/nmtService";
import { listTTSServices, TTSServiceDetailsResponse } from "../services/ttsService";
import { useToastWithDeduplication } from "../hooks/useToastWithDeduplication";

const PipelinePage: React.FC = () => {
  const toast = useToastWithDeduplication();
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const [sourceLanguage, setSourceLanguage] = useState("");
  const [targetLanguage, setTargetLanguage] = useState("");
  const [asrServiceId, setAsrServiceId] = useState<string>("");
  const [nmtServiceId, setNmtServiceId] = useState<string>("");
  const [ttsServiceId, setTtsServiceId] = useState<string>("");
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);

  const {
    isLoading,
    result,
    isRecording,
    timer,
    startRecording,
    stopRecording,
    pendingAudio,
    processRecordedAudio,
    processUploadedAudio,
    setProcessRecordedAudioCallback,
    runPipeline,
  } = usePipeline();

  // Fetch available services
  const { data: asrServices } = useQuery<ASRServiceDetails[]>({
    queryKey: ["asr-services"],
    queryFn: listASRServices,
    staleTime: 5 * 60 * 1000,
  });

  const { data: nmtServices } = useQuery({
    queryKey: ["nmt-services", isAuthenticated],
    queryFn: listNMTServices,
    staleTime: 5 * 60 * 1000,
  });

  const { data: ttsServices } = useQuery<TTSServiceDetailsResponse[]>({
    queryKey: ["tts-services"],
    queryFn: listTTSServices,
    staleTime: 5 * 60 * 1000,
  });

  const hasRequiredConfig = () =>
    !!sourceLanguage?.trim() &&
    !!targetLanguage?.trim() &&
    !!asrServiceId?.trim() &&
    !!nmtServiceId?.trim() &&
    !!ttsServiceId?.trim();

  const ensureConfigOrToast = () => {
    if (!sourceLanguage?.trim() || !targetLanguage?.trim()) {
      toast({
        title: "Language Required",
        description: "Please select both source and target languages before recording or uploading audio.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return false;
    }
    if (!asrServiceId?.trim() || !nmtServiceId?.trim() || !ttsServiceId?.trim()) {
      toast({
        title: "Service Selection Required",
        description: "Please select ASR, NMT, and TTS services before recording or uploading audio.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return false;
    }
    return true;
  };

  const canRunPipeline = hasRequiredConfig() && !isLoading;
  const canSubmit = hasRequiredConfig() && !!pendingAudio && !isLoading;

  const handleRecordClick = async () => {
    if (!ensureConfigOrToast()) {
      return;
    }

    if (isRecording) {
      stopRecording();
    } else {
      setUploadedFileName(null);
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

    if (!ensureConfigOrToast()) {
      event.target.value = "";
      return;
    }

    try {
      setUploadedFileName(file.name);
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

  const handleRunPipeline = () => {
    if (!ensureConfigOrToast()) {
      return;
    }
    if (!pendingAudio) {
      toast({
        title: "Audio Required",
        description: "Please record or upload an audio file before running the pipeline.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    runPipeline(
      sourceLanguage,
      targetLanguage,
      asrServiceId,
      nmtServiceId,
      ttsServiceId
    );
  };

  return (
    <>
      <Head>
        <title>Speech to Speech | AI4Inclusion Console</title>
        <meta
          name="description"
          content="Transform spoken input into translated speech output using chained AI models"
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
                  {getServiceTitle("pipeline")}
                </Heading>
                <Text color="gray.600" fontSize="sm" userSelect="none" cursor="default">
                  {getServiceDescription("pipeline")}
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
            <GridItem pt={0} mt={0} alignSelf="flex-start">
              <VStack spacing={6} align="stretch" pt={0} mt={0}>
                {/* Source Language */}
                <FormControl>
                  <FormLabel className="dview-service-try-option-title">
                    Source Language{" "}
                    <Text as="span" color="red.500">*</Text>
                  </FormLabel>
                  <Select
                    value={sourceLanguage}
                    onChange={(e) => setSourceLanguage(e.target.value)}
                    placeholder="Select"
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
                    Target Language{" "}
                    <Text as="span" color="red.500">*</Text>
                  </FormLabel>
                  <Select
                    value={targetLanguage}
                    onChange={(e) => setTargetLanguage(e.target.value)}
                    placeholder="Select"
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
                    ASR Service{" "}
                    <Text as="span" color="red.500">*</Text>
                  </FormLabel>
                  <Select
                    value={asrServiceId}
                    onChange={(e) => setAsrServiceId(e.target.value)}
                    placeholder="Select"
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
                    NMT Service{" "}
                    <Text as="span" color="red.500">*</Text>
                  </FormLabel>
                  <Select
                    value={nmtServiceId}
                    onChange={(e) => setNmtServiceId(e.target.value)}
                    placeholder="Select"
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
                    TTS Service{" "}
                    <Text as="span" color="red.500">*</Text>
                  </FormLabel>
                  <Select
                    value={ttsServiceId}
                    onChange={(e) => setTtsServiceId(e.target.value)}
                    placeholder="Select"
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

                {/* Audio Input - grouped like ASR */}
                <Box>
                  <FormLabel className="dview-service-try-option-title" mb={4}>
                    Audio Input{" "}
                    <Text as="span" color="red.500">
                      *
                    </Text>
                  </FormLabel>

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

                  <VStack spacing={4} mt={4} align="stretch">
                    {/* Record Instruction + Button (boxed, like ASR AudioRecorder) */}
                    <Box
                      p={3}
                      borderRadius="md"
                      borderWidth="1px"
                      borderColor="gray.200"
                      bg="gray.50"
                    >
                      <Text fontSize="sm" color="gray.600" mb={2}>
                        Click Record to capture speech using your microphone (max{" "}
                        {formatDuration(MAX_RECORDING_DURATION)} seconds).
                      </Text>
                      <Button
                        leftIcon={
                          isRecording ? <FaMicrophoneSlash /> : <FaMicrophone />
                        }
                        colorScheme={isRecording ? "red" : "orange"}
                        variant={isRecording ? "solid" : "outline"}
                        onClick={handleRecordClick}
                        disabled={!canRunPipeline || isLoading}
                        w="full"
                        h="50px"
                      >
                        {isRecording ? "Stop" : "Record"}
                      </Button>
                    </Box>

                    {/* Upload Instruction + Button (boxed, like ASR AudioRecorder) */}
                    <Box
                      p={3}
                      borderRadius="md"
                      borderWidth="1px"
                      borderColor="gray.200"
                      bg="gray.50"
                    >
                      <Text fontSize="sm" color="gray.600" mb={2}>
                        Click Upload to choose an audio file (MP3 or WAV) from your
                        device to run through the pipeline.
                      </Text>
                      <Button
                        as="label"
                        leftIcon={<FaUpload />}
                        colorScheme="blue"
                        variant="outline"
                        cursor="pointer"
                        disabled={!canRunPipeline || isLoading || isRecording}
                        w="full"
                        h="50px"
                      >
                        Upload
                        <input
                          type="file"
                          accept="audio/*"
                          onChange={handleFileUpload}
                          style={{ display: "none" }}
                        />
                      </Button>
                      {uploadedFileName && (
                        <Text
                          fontSize="sm"
                          color="gray.700"
                          mt={2}
                          noOfLines={1}
                          title={uploadedFileName}
                        >
                          Uploaded: {uploadedFileName}
                        </Text>
                      )}
                    </Box>

                    {/* Instruction above Run Pipeline */}
                    <Text fontSize="sm" color="gray.600">
                      After recording or uploading audio, click Run Pipeline to
                      generate the transcribed text, translated text, and synthesized
                      speech.
                    </Text>

                    {/* Run Pipeline Button */}
                    <Button
                      colorScheme="orange"
                      size="lg"
                      onClick={handleRunPipeline}
                      isLoading={isLoading}
                      loadingText="Running..."
                      isDisabled={!canSubmit}
                      w="full"
                    >
                      Run Pipeline
                    </Button>
                  </VStack>
                </Box>
              </VStack>
            </GridItem>

            {/* Results Panel */}
            <GridItem pt={0} mt={0} alignSelf="flex-start">
              <VStack spacing={6} align="stretch" pt={0} mt={0}>
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
                {result && (
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
                      value={result.sourceText}
                      rows={4}
                    />
                  </Box>
                )}

                {/* Target Text */}
                {result && (
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
                      value={result.targetText}
                      rows={4}
                    />
                  </Box>
                )}

                {/* Audio Player */}
                {result && result.audio && (
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
