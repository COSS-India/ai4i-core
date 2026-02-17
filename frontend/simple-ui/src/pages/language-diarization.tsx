// Language Diarization service testing page

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
  VStack,
} from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import Head from "next/head";
import React, { useState, useEffect } from "react";
import AudioRecorder from "../components/asr/AudioRecorder";
import ContentLayout from "../components/common/ContentLayout";
import { performLanguageDiarizationInference, listLanguageDiarizationServices } from "../services/languageDiarizationService";
import { useAudioRecorder } from "../hooks/useAudioRecorder";
import { useToastWithDeduplication } from "../hooks/useToastWithDeduplication";

const LanguageDiarizationPage: React.FC = () => {
  const toast = useToastWithDeduplication();
  const [serviceId, setServiceId] = useState<string>("");
  const [audioData, setAudioData] = useState<string | null>(null);
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [responseTime, setResponseTime] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  // Fetch available Language Diarization services
  const { data: languageDiarizationServices, isLoading: servicesLoading } = useQuery({
    queryKey: ["language-diarization-services"],
    queryFn: listLanguageDiarizationServices,
    staleTime: 10 * 60 * 1000, // 10 minutes
  });

  // Auto-select first available Language Diarization service when list loads
  useEffect(() => {
    if (!languageDiarizationServices || languageDiarizationServices.length === 0) return;
    if (!serviceId) {
      // If no service selected, select first available
      setServiceId(languageDiarizationServices[0].service_id);
    }
  }, [languageDiarizationServices, serviceId]);

  const {
    isRecording,
    timer,
    startRecording,
    stopRecording,
  } = useAudioRecorder({
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

  const handleRecordingChange = (isRecording: boolean) => {
    if (isRecording) {
      startRecording();
    } else {
      stopRecording();
    }
  };

  const handleAudioReady = (audioBase64: string) => {
    // Store audio data instead of immediately processing
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
      toast({
        title: "No Audio",
        description: "Please record or upload audio first.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    if (!serviceId) {
      toast({
        title: "Service Required",
        description: "Please select a Language Diarization service.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    setFetching(true);
    setError(null);
    setFetched(false);

    try {
      const startTime = Date.now();
      const response = await performLanguageDiarizationInference(
        audioData,
        serviceId
      );
      const endTime = Date.now();
      const calculatedTime = ((endTime - startTime) / 1000).toFixed(2);

      setResult(response.data);
      setResponseTime(parseFloat(calculatedTime));
      setFetched(true);
    } catch (err: any) {
      // Prioritize API error message from response
      let errorMessage = "Failed to perform language diarization";
      
      if (err?.response?.data?.detail?.message) {
        errorMessage = err.response.data.detail.message;
      } else if (err?.response?.data?.message) {
        errorMessage = err.response.data.message;
      } else if (err?.response?.data?.detail) {
        if (typeof err.response.data.detail === 'string') {
          errorMessage = err.response.data.detail;
        }
      } else if (err?.message) {
        errorMessage = err.message;
      }
      
      setError(errorMessage);
      toast({
        title: "Error",
        description: errorMessage,
        status: "error",
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setFetching(false);
    }
  };

  const clearResults = () => {
    setFetched(false);
    setResult(null);
    setAudioData(null);
    setError(null);
  };

  return (
    <>
      <Head>
        <title>Language Diarization | AI4Inclusion Console</title>
        <meta
          name="description"
          content="Test Language Diarization to identify language changes in audio"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={8} w="full">
          {/* Page Header */}
          <Box textAlign="center">
            <Heading size="xl" color="gray.800" mb={2} userSelect="none" cursor="default" tabIndex={-1}>
              Language Diarization
            </Heading>
            <Text color="gray.600" fontSize="lg" userSelect="none" cursor="default">
              Identify when language changes occur within spoken audio. Segment audio based on the language being spoken.
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
              <FormControl>
                <FormLabel fontSize="sm" fontWeight="semibold">
                  Language Diarization Service:
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
                    placeholder="Select a Language Diarization service"
                    disabled={fetching}
                    size="md"
                    borderColor="gray.300"
                    _focus={{
                      borderColor: "orange.400",
                      boxShadow: "0 0 0 1px var(--chakra-colors-orange-400)",
                    }}
                  >
                    {languageDiarizationServices?.map((service) => (
                      <option key={service.service_id} value={service.service_id}>
                        {service.name || service.service_id} {service.model_version ? `(${service.model_version})` : ''}
                      </option>
                    ))}
                  </Select>
                )}
                {serviceId && languageDiarizationServices && (
                  <Box mt={2} p={3} bg="orange.50" borderRadius="md" border="1px" borderColor="orange.200">
                    {(() => {
                      const selectedService = languageDiarizationServices.find(s => s.service_id === serviceId);
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

              <Box>
                <Text mb={4} fontSize="sm" fontWeight="semibold">
                  Audio Input:
                </Text>
                <AudioRecorder
                  onAudioReady={handleAudioReady}
                  isRecording={isRecording}
                  onRecordingChange={handleRecordingChange}
                  sampleRate={16000}
                  disabled={fetching}
                  timer={timer}
                />
              </Box>

              {/* Audio Status */}
              {audioData && (
                <Box
                  p={3}
                  bg="green.50"
                  borderRadius="md"
                  border="1px"
                  borderColor="green.200"
                >
                  <Text fontSize="sm" color="green.700" fontWeight="semibold">
                    ✓ Audio ready for processing
                  </Text>
                </Box>
              )}

              {/* Submit Button */}
              <Button
                colorScheme="orange"
                onClick={handleSubmit}
                isLoading={fetching}
                loadingText="Processing..."
                size="md"
                w="full"
                isDisabled={!audioData || fetching}
              >
                Submit for Diarization
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

              {/* Metrics Box */}
              {fetched && (
                <Box
                  p={4}
                  bg="orange.50"
                  borderRadius="md"
                  border="1px"
                  borderColor="orange.200"
                >
                  <HStack spacing={6}>
                    <VStack align="start" spacing={0}>
                      <Text fontSize="xs" color="gray.600">
                        Response Time
                      </Text>
                      <Text fontSize="lg" fontWeight="bold" color="gray.800">
                        {responseTime.toFixed(2)} seconds
                      </Text>
                    </VStack>
                  </HStack>
                </Box>
              )}

              {fetched && result && (() => {
                // Extract data - handle both result.output[0] and direct result structure
                const data = result.output && result.output[0] ? result.output[0] : result;
                const segments = data.segments || [];
                const languages = data.languages || [];
                // Extract unique languages from segments if not provided directly
                const uniqueLanguages = languages.length > 0 
                  ? languages 
                  : Array.from(new Set(segments.map((s: any) => s.language).filter(Boolean)));
                const numLanguages = data.num_languages || uniqueLanguages.length || 0;
                
                const formatTime = (seconds: number) => {
                  const mins = Math.floor(seconds / 60);
                  const secs = (seconds % 60).toFixed(2);
                  return mins > 0 ? `${mins}:${secs.padStart(5, '0')}` : `${secs}s`;
                };

                const getLanguageColor = (language: string) => {
                  const languageIndex = uniqueLanguages.indexOf(language);
                  const colors = ["orange", "blue", "green", "purple", "pink", "teal", "cyan", "yellow"];
                  return colors[languageIndex % colors.length] || "gray";
                };

                // Check if we have structured data to display
                const hasStructuredData = segments.length > 0 || numLanguages > 0;

                return (
                  <Box
                    p={4}
                    bg="gray.50"
                    borderRadius="md"
                    border="1px"
                    borderColor="gray.200"
                  >
                    <Text fontSize="sm" fontWeight="semibold" mb={3} color="gray.700">
                      Language Diarization Results:
                    </Text>
                    
                    {hasStructuredData ? (
                      <>
                        {/* Summary */}
                        <HStack spacing={4} mb={4}>
                          <Box
                            p={3}
                            bg="orange.100"
                            borderRadius="md"
                            border="1px"
                            borderColor="orange.300"
                          >
                            <Text fontSize="xs" color="gray.600" mb={1}>
                              Total Languages
                            </Text>
                            <Text fontSize="lg" fontWeight="bold" color="orange.700">
                              {numLanguages}
                            </Text>
                          </Box>
                          <Box
                            p={3}
                            bg="blue.100"
                            borderRadius="md"
                            border="1px"
                            borderColor="blue.300"
                          >
                            <Text fontSize="xs" color="gray.600" mb={1}>
                              Total Segments
                            </Text>
                            <Text fontSize="lg" fontWeight="bold" color="blue.700">
                              {segments.length}
                            </Text>
                          </Box>
                        </HStack>

                        {/* Languages List */}
                        {uniqueLanguages.length > 0 && (
                          <Box mb={4}>
                            <Text fontSize="xs" fontWeight="semibold" color="gray.600" mb={2}>
                              Detected Languages:
                            </Text>
                            <HStack spacing={2} flexWrap="wrap">
                              {uniqueLanguages.map((language: string, idx: number) => {
                                const colorScheme = getLanguageColor(language);
                                return (
                                  <Box
                                    key={language}
                                    px={3}
                                    py={1}
                                    bg={`${colorScheme}.100`}
                                    borderRadius="full"
                                    border="1px"
                                    borderColor={`${colorScheme}.300`}
                                  >
                                    <Text fontSize="sm" fontWeight="semibold" color={`${colorScheme}.700`}>
                                      {language.toUpperCase()}
                                    </Text>
                                  </Box>
                                );
                              })}
                            </HStack>
                          </Box>
                        )}

                        {/* Segments Timeline */}
                        {segments.length > 0 && (
                          <Box>
                            <Text fontSize="xs" fontWeight="semibold" color="gray.600" mb={3}>
                              Timeline Segments (sorted by start time):
                            </Text>
                            <Box
                              p={3}
                              bg="white"
                              borderRadius="md"
                              maxH="400px"
                              overflowY="auto"
                              border="1px"
                              borderColor="gray.200"
                            >
                              <VStack align="stretch" spacing={2}>
                                {(() => {
                                  // Sort segments by start_time or start
                                  const sortedSegments = [...segments].sort(
                                    (a: any, b: any) => {
                                      const aStart = a.start_time !== undefined ? a.start_time : a.start;
                                      const bStart = b.start_time !== undefined ? b.start_time : b.start;
                                      return aStart - bStart;
                                    }
                                  );

                                  return sortedSegments.map((segment: any, idx: number) => {
                                    const startTime = segment.start_time !== undefined ? segment.start_time : segment.start;
                                    const endTime = segment.end_time !== undefined ? segment.end_time : segment.end;
                                    const duration = segment.duration !== undefined 
                                      ? segment.duration 
                                      : (endTime - startTime);
                                    const language = segment.language || "Unknown";
                                    const colorScheme = getLanguageColor(language);

                                    return (
                                      <Box
                                        key={idx}
                                        p={3}
                                        bg={`${colorScheme}.50`}
                                        borderRadius="md"
                                        border="1px"
                                        borderColor={`${colorScheme}.200`}
                                      >
                                        <HStack justify="space-between" align="start" mb={2}>
                                          <HStack spacing={2}>
                                            <Box
                                              px={2}
                                              py={1}
                                              bg={`${colorScheme}.200`}
                                              borderRadius="md"
                                            >
                                              <Text fontSize="xs" fontWeight="bold" color={`${colorScheme}.800`}>
                                                {language.toUpperCase()}
                                              </Text>
                                            </Box>
                                          </HStack>
                                          <VStack align="end" spacing={0}>
                                            <Text fontSize="xs" color="gray.600">
                                              Duration: {formatTime(duration)}
                                            </Text>
                                          </VStack>
                                        </HStack>
                                        <HStack spacing={2} fontSize="xs" color="gray.600">
                                          <Text>
                                            <Text as="span" fontWeight="semibold">Start:</Text> {formatTime(startTime)}
                                          </Text>
                                          <Text>•</Text>
                                          <Text>
                                            <Text as="span" fontWeight="semibold">End:</Text> {formatTime(endTime)}
                                          </Text>
                                        </HStack>
                                      </Box>
                                    );
                                  });
                                })()}
                              </VStack>
                            </Box>
                          </Box>
                        )}
                      </>
                    ) : (
                      /* Fallback to JSON if structure is different */
                      <Box
                        p={3}
                        bg="white"
                        borderRadius="md"
                        maxH="400px"
                        overflowY="auto"
                      >
                        <Text as="pre" fontSize="xs" whiteSpace="pre-wrap" wordBreak="break-word">
                          {JSON.stringify(result, null, 2)}
                        </Text>
                      </Box>
                    )}
                  </Box>
                );
              })()}

                {/* Language Diarization Results */}
                {fetched && result && (() => {
                  // Extract data - handle both result.output[0] and direct result structure
                  const data = result.output && result.output[0] ? result.output[0] : result;
                  const segments = data.segments || [];
                  const languages = data.languages || [];
                  // Extract unique languages from segments if not provided directly
                  const uniqueLanguages = languages.length > 0 
                    ? languages 
                    : Array.from(new Set(segments.map((s: any) => s.language).filter(Boolean)));
                  const numLanguages = data.num_languages || uniqueLanguages.length || 0;
                  
                  const formatTime = (seconds: number) => {
                    const mins = Math.floor(seconds / 60);
                    const secs = (seconds % 60).toFixed(2);
                    return mins > 0 ? `${mins}:${secs.padStart(5, '0')}` : `${secs}s`;
                  };

                  const getLanguageColor = (language: string) => {
                    const languageIndex = uniqueLanguages.indexOf(language);
                    const colors = ["orange", "blue", "green", "purple", "pink", "teal", "cyan", "yellow"];
                    return colors[languageIndex % colors.length] || "gray";
                  };

                  // Check if we have structured data to display
                  const hasStructuredData = segments.length > 0 || numLanguages > 0;

                  return (
                    <>
                      <Box
                        p={4}
                        bg="gray.50"
                        borderRadius="md"
                        border="1px"
                        borderColor="gray.200"
                      >
                        <Text fontSize="sm" fontWeight="semibold" mb={3} color="gray.700">
                          Language Diarization Results:
                        </Text>
                        
                        {hasStructuredData ? (
                          <>
                            {/* Summary */}
                            <HStack spacing={4} mb={4}>
                              <Box
                                p={3}
                                bg="orange.100"
                                borderRadius="md"
                                border="1px"
                                borderColor="orange.300"
                              >
                                <Text fontSize="xs" color="gray.600" mb={1}>
                                  Total Languages
                                </Text>
                                <Text fontSize="lg" fontWeight="bold" color="orange.700">
                                  {numLanguages}
                                </Text>
                              </Box>
                              <Box
                                p={3}
                                bg="blue.100"
                                borderRadius="md"
                                border="1px"
                                borderColor="blue.300"
                              >
                                <Text fontSize="xs" color="gray.600" mb={1}>
                                  Total Segments
                                </Text>
                                <Text fontSize="lg" fontWeight="bold" color="blue.700">
                                  {segments.length}
                                </Text>
                              </Box>
                            </HStack>

                            {/* Languages List */}
                            {uniqueLanguages.length > 0 && (
                              <Box mb={4}>
                                <Text fontSize="xs" fontWeight="semibold" color="gray.600" mb={2}>
                                  Detected Languages:
                                </Text>
                                <HStack spacing={2} flexWrap="wrap">
                                  {uniqueLanguages.map((language: string, idx: number) => {
                                    const colorScheme = getLanguageColor(language);
                                    return (
                                      <Box
                                        key={language}
                                        px={3}
                                        py={1}
                                        bg={`${colorScheme}.100`}
                                        borderRadius="full"
                                        border="1px"
                                        borderColor={`${colorScheme}.300`}
                                      >
                                        <Text fontSize="sm" fontWeight="semibold" color={`${colorScheme}.700`}>
                                          {language.toUpperCase()}
                                        </Text>
                                      </Box>
                                    );
                                  })}
                                </HStack>
                              </Box>
                            )}

                            {/* Segments Timeline */}
                            {segments.length > 0 && (
                              <Box>
                                <Text fontSize="xs" fontWeight="semibold" color="gray.600" mb={3}>
                                  Timeline Segments (sorted by start time):
                                </Text>
                                <Box
                                  p={3}
                                  bg="white"
                                  borderRadius="md"
                                  maxH="400px"
                                  overflowY="auto"
                                  border="1px"
                                  borderColor="gray.200"
                                >
                                  <VStack align="stretch" spacing={2}>
                                    {(() => {
                                      // Sort segments by start_time or start
                                      const sortedSegments = [...segments].sort(
                                        (a: any, b: any) => {
                                          const aStart = a.start_time !== undefined ? a.start_time : a.start;
                                          const bStart = b.start_time !== undefined ? b.start_time : b.start;
                                          return aStart - bStart;
                                        }
                                      );

                                      return sortedSegments.map((segment: any, idx: number) => {
                                        const startTime = segment.start_time !== undefined ? segment.start_time : segment.start;
                                        const endTime = segment.end_time !== undefined ? segment.end_time : segment.end;
                                        const duration = segment.duration !== undefined 
                                          ? segment.duration 
                                          : (endTime - startTime);
                                        const language = segment.language || "Unknown";
                                        const colorScheme = getLanguageColor(language);

                                        return (
                                          <Box
                                            key={idx}
                                            p={3}
                                            bg={`${colorScheme}.50`}
                                            borderRadius="md"
                                            border="1px"
                                            borderColor={`${colorScheme}.200`}
                                          >
                                            <HStack justify="space-between" align="start" mb={2}>
                                              <HStack spacing={2}>
                                                <Box
                                                  px={2}
                                                  py={1}
                                                  bg={`${colorScheme}.200`}
                                                  borderRadius="md"
                                                >
                                                  <Text fontSize="xs" fontWeight="bold" color={`${colorScheme}.800`}>
                                                    {language.toUpperCase()}
                                                  </Text>
                                                </Box>
                                              </HStack>
                                              <VStack align="end" spacing={0}>
                                                <Text fontSize="xs" color="gray.600">
                                                  Duration: {formatTime(duration)}
                                                </Text>
                                              </VStack>
                                            </HStack>
                                            <HStack spacing={2} fontSize="xs" color="gray.600">
                                              <Text>
                                                <Text as="span" fontWeight="semibold">Start:</Text> {formatTime(startTime)}
                                              </Text>
                                              <Text>•</Text>
                                              <Text>
                                                <Text as="span" fontWeight="semibold">End:</Text> {formatTime(endTime)}
                                              </Text>
                                            </HStack>
                                          </Box>
                                        );
                                      });
                                    })()}
                                  </VStack>
                                </Box>
                              </Box>
                            )}
                          </>
                        ) : (
                          /* Fallback to JSON if structure is different */
                          <Box
                            p={3}
                            bg="white"
                            borderRadius="md"
                            maxH="400px"
                            overflowY="auto"
                          >
                            <Text as="pre" fontSize="xs" whiteSpace="pre-wrap" wordBreak="break-word">
                              {JSON.stringify(result, null, 2)}
                            </Text>
                          </Box>
                        )}
                      </Box>

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
                  );
                })()}
            </VStack>
          </GridItem>
        </Grid>
        </VStack>
      </ContentLayout>
    </>
  );
};

export default LanguageDiarizationPage;
