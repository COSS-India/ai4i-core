// Speaker Diarization service testing page

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
import React, { useState, useEffect } from "react";
import AudioRecorder from "../components/asr/AudioRecorder";
import ContentLayout from "../components/common/ContentLayout";
import { performSpeakerDiarizationInference, listSpeakerDiarizationServices } from "../services/speakerDiarizationService";
import { useAudioRecorder } from "../hooks/useAudioRecorder";
import { extractErrorInfo } from "../utils/errorHandler";

const SpeakerDiarizationPage: React.FC = () => {
  const toast = useToast();
  const [serviceId, setServiceId] = useState<string>("");
  const [audioData, setAudioData] = useState<string | null>(null);
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [responseTime, setResponseTime] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  // Fetch available Speaker Diarization services
  const { data: speakerDiarizationServices, isLoading: servicesLoading } = useQuery({
    queryKey: ["speaker-diarization-services"],
    queryFn: listSpeakerDiarizationServices,
    staleTime: 10 * 60 * 1000, // 10 minutes
  });

  // Auto-select first available Speaker Diarization service when list loads
  useEffect(() => {
    if (!speakerDiarizationServices || speakerDiarizationServices.length === 0) return;
    if (!serviceId) {
      // If no service selected, select first available
      setServiceId(speakerDiarizationServices[0].service_id);
    }
  }, [speakerDiarizationServices, serviceId]);

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
        description: "Please select a Speaker Diarization service.",
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
      const response = await performSpeakerDiarizationInference(
        audioData,
        serviceId
      );
      const endTime = Date.now();
      const calculatedTime = ((endTime - startTime) / 1000).toFixed(2);

      setResult(response.data);
      setResponseTime(parseFloat(calculatedTime));
      setFetched(true);
    } catch (err: any) {
      // Use centralized error handler
      const { title: errorTitle, message: errorMessage } = extractErrorInfo(err);
      
      setError(errorMessage);
      toast({
        title: errorTitle,
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
        <title>Speaker Diarization | AI4Inclusion Console</title>
        <meta
          name="description"
          content="Test Speaker Diarization to separate conversations by speaker"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={8} w="full">
          {/* Page Header */}
          <Box textAlign="center">
            <Heading size="xl" color="gray.800" mb={2}>
              Speaker Diarization
            </Heading>
            <Text color="gray.600" fontSize="lg">
              Separate conversations into segments based on who is speaking. Identify different speakers in audio recordings and segment the audio accordingly.
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
                  Speaker Diarization Service:
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
                    placeholder="Select a Speaker Diarization service"
                    disabled={fetching}
                    size="md"
                    borderColor="gray.300"
                    _focus={{
                      borderColor: "orange.400",
                      boxShadow: "0 0 0 1px var(--chakra-colors-orange-400)",
                    }}
                  >
                    {speakerDiarizationServices?.map((service) => (
                      <option key={service.service_id} value={service.service_id}>
                        {service.name || service.service_id} {service.model_version ? `(${service.model_version})` : ''}
                      </option>
                    ))}
                  </Select>
                )}
                {serviceId && speakerDiarizationServices && (
                  <Box mt={2} p={3} bg="orange.50" borderRadius="md" border="1px" borderColor="orange.200">
                    {(() => {
                      const selectedService = speakerDiarizationServices.find(s => s.service_id === serviceId);
                      return selectedService ? (
                        <>
                          <Text fontSize="sm" color="gray.700" mb={1}>
                            <strong>Service ID:</strong> {selectedService.service_id}
                          </Text>
                          {selectedService.serviceDescription && (
                            <Text fontSize="sm" color="gray.700" mb={1}>
                              <strong>Description:</strong> {selectedService.serviceDescription}
                            </Text>
                          )}
                          {selectedService.supported_languages.length > 0 && (
                            <Text fontSize="sm" color="gray.700">
                              <strong>Languages:</strong> {selectedService.supported_languages.join(', ')}
                            </Text>
                          )}
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

              {/* Speaker Diarization Results */}
              {fetched && result && (() => {
                // Extract data from API response structure: { taskType, output: [{ segments, speakers, ... }], config }
                const outputData = result.output && Array.isArray(result.output) && result.output.length > 0 
                  ? result.output[0] 
                  : null;
                
                // If no output data, check if result itself has the structure
                const data = outputData || (result.segments !== undefined || result.speakers !== undefined ? result : null);
                
                if (!data) {
                  // If structure is completely different, show error message
                  return (
                    <Box
                      p={4}
                      bg="yellow.50"
                      borderRadius="md"
                      border="1px"
                      borderColor="yellow.200"
                    >
                      <Text fontSize="sm" color="yellow.800" fontWeight="semibold" mb={2}>
                        Unexpected Response Format
                      </Text>
                      <Text fontSize="xs" color="yellow.700">
                        The API response structure is not recognized. Please check the API response format.
                      </Text>
                    </Box>
                  );
                }

                const segments = data.segments || [];
                const speakers = data.speakers || [];
                const numSpeakers = data.num_speakers !== undefined ? data.num_speakers : (speakers.length || 0);
                const totalSegments = data.total_segments !== undefined ? data.total_segments : segments.length;
                
                const formatTime = (seconds: number) => {
                  const mins = Math.floor(seconds / 60);
                  const secs = (seconds % 60).toFixed(2);
                  return mins > 0 ? `${mins}:${secs.padStart(5, '0')}` : `${secs}s`;
                };

                const getSpeakerColor = (speaker: string) => {
                  const speakerIndex = speakers.indexOf(speaker);
                  const colors = ["orange", "blue", "green", "purple", "pink", "teal", "cyan", "yellow"];
                  return colors[speakerIndex % colors.length] || "gray";
                };

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
                        Diarization Results:
                      </Text>
                      
                      {/* Summary - Always show, even if empty */}
                      <HStack spacing={4} mb={4}>
                        <Box
                          p={3}
                          bg="orange.100"
                          borderRadius="md"
                          border="1px"
                          borderColor="orange.300"
                        >
                          <Text fontSize="xs" color="gray.600" mb={1}>
                            Total Speakers
                          </Text>
                          <Text fontSize="lg" fontWeight="bold" color="orange.700">
                            {numSpeakers}
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
                            {totalSegments}
                          </Text>
                        </Box>
                      </HStack>

                      {/* Show message if no speakers/segments detected */}
                      {segments.length === 0 && numSpeakers === 0 ? (
                        <Box
                          p={4}
                          bg="blue.50"
                          borderRadius="md"
                          border="1px"
                          borderColor="blue.200"
                          textAlign="center"
                        >
                          <Text fontSize="sm" color="blue.700" fontWeight="semibold" mb={1}>
                            No Speakers Detected
                          </Text>
                          <Text fontSize="xs" color="blue.600">
                            The audio processing completed, but no speakers or segments were identified in the audio.
                            This may occur if the audio is too short, contains only silence, or has poor quality.
                          </Text>
                        </Box>
                      ) : (
                        <>
                          {/* Speakers List */}
                          {speakers.length > 0 && (
                            <Box mb={4}>
                              <Text fontSize="xs" fontWeight="semibold" color="gray.600" mb={2}>
                                Identified Speakers:
                              </Text>
                              <HStack spacing={2} flexWrap="wrap">
                                {speakers.map((speaker: string, idx: number) => {
                                  const colorScheme = getSpeakerColor(speaker);
                                  return (
                                    <Box
                                      key={speaker}
                                      px={3}
                                      py={1}
                                      bg={`${colorScheme}.100`}
                                      borderRadius="full"
                                      border="1px"
                                      borderColor={`${colorScheme}.300`}
                                    >
                                      <Text fontSize="sm" fontWeight="semibold" color={`${colorScheme}.700`}>
                                        {speaker}
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
                                        return (aStart || 0) - (bStart || 0);
                                      }
                                    );

                                    return sortedSegments.map((segment: any, idx: number) => {
                                      const startTime = segment.start_time !== undefined ? segment.start_time : segment.start;
                                      const endTime = segment.end_time !== undefined ? segment.end_time : segment.end;
                                      const duration = segment.duration !== undefined 
                                        ? segment.duration 
                                        : (endTime && startTime ? endTime - startTime : 0);
                                      const speaker = segment.speaker || "Unknown";
                                      const colorScheme = getSpeakerColor(speaker);

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
                                                  {speaker}
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
                                              <Text as="span" fontWeight="semibold">Start:</Text> {formatTime(startTime || 0)}
                                            </Text>
                                            <Text>•</Text>
                                            <Text>
                                              <Text as="span" fontWeight="semibold">End:</Text> {formatTime(endTime || 0)}
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
                      )}
                    </Box>

                    {/* Clear Results Button */}
                    <Box textAlign="center">
                      <Button
                        onClick={clearResults}
                        variant="outline"
                        size="sm"
                        colorScheme="gray"
                      >
                        Clear Results
                      </Button>
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

export default SpeakerDiarizationPage;
