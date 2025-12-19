// Audio Language Detection service testing page

import {
  Box,
  Button,
  Grid,
  GridItem,
  Heading,
  HStack,
  Progress,
  Text,
  useToast,
  VStack,
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useState } from "react";
import AudioRecorder from "../components/asr/AudioRecorder";
import ContentLayout from "../components/common/ContentLayout";
import { performAudioLanguageDetectionInference } from "../services/audioLanguageDetectionService";
import { useAudioRecorder } from "../hooks/useAudioRecorder";

const AudioLanguageDetectionPage: React.FC = () => {
  const toast = useToast();
  const [audioData, setAudioData] = useState<string | null>(null);
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [responseTime, setResponseTime] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

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

    setFetching(true);
    setError(null);
    setFetched(false);

    try {
      const startTime = Date.now();
      const response = await performAudioLanguageDetectionInference(
        audioData,
        "ai4bharat/audio-lang-detection"
      );
      const endTime = Date.now();
      const calculatedTime = ((endTime - startTime) / 1000).toFixed(2);

      setResult(response.data);
      setResponseTime(parseFloat(calculatedTime));
      setFetched(true);
    } catch (err: any) {
      setError(err.message || "Failed to perform audio language detection");
      toast({
        title: "Error",
        description: err.message || "Failed to perform audio language detection",
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
        <title>Audio Language Detection | AI4Inclusion Console</title>
        <meta
          name="description"
          content="Test Audio Language Detection to detect spoken language from audio"
        />
      </Head>

      <ContentLayout>
        <Grid
          templateColumns={{ base: "1fr", lg: "1fr 1fr" }}
          gap={8}
          w="full"
          maxW="1400px"
          mx="auto"
        >
          {/* Left Column - Service Details */}
          <GridItem>
            <VStack spacing={6} align="stretch">
              <Heading size="lg" color="gray.800">
                Audio Language Detection
              </Heading>
              <Text color="gray.600" fontSize="md">
                Detect the spoken language directly from an audio file. Identify which language is being spoken in audio recordings.
              </Text>
            </VStack>
          </GridItem>

          {/* Right Column - Try it out here! */}
          <GridItem>
            <VStack spacing={6} align="stretch">
              <Heading size="md" color="gray.800">
                Try it out here!
              </Heading>

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
                Submit for Detection
              </Button>

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

              {fetching && (
                <Box>
                  <Text mb={2} fontSize="sm" color="gray.600">
                    Processing audio...
                  </Text>
                  <Progress size="xs" isIndeterminate colorScheme="gray" />
                </Box>
              )}

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

              {fetched && result && (() => {
                console.log("res",result,result.output[0],result.output[0].all_scores.predicted_language);
                
                // Extract data - handle both result.output[0] and direct result structure
                const data = result.output && result.output[0] ? result.output[0] : result;
                
                // If we have multiple outputs, use the first one
                const outputItem = result.output && result.output.length > 0 
                  ? result.output[0] 
                  : data;

                // Extract language - handle predicted_language format "ml: Malayalam"
                let language = "Unknown";
                const predictedLanguage = outputItem.all_scores?.predicted_language || data?.all_scores?.predicted_language;
                
                if (predictedLanguage) {
                  // Parse format like "ml: Malayalam" to extract "Malayalam"
                  const parts = predictedLanguage.split(":");
                  if (parts.length > 1) {
                    language = parts.slice(1).join(":").trim(); // Join in case language name contains ":"
                  } else {
                    language = predictedLanguage.trim();
                  }
                } else {
                  // Fallback to other possible fields
                  language = outputItem.detectedLanguage || outputItem.language || data.detectedLanguage || data.language || "Unknown";
                }
                
                const conf = outputItem.confidence !== undefined ? outputItem.confidence : (data.confidence !== undefined ? data.confidence : null);

                return (
                  <Box
                    p={4}
                    bg="gray.50"
                    borderRadius="md"
                    border="1px"
                    borderColor="gray.200"
                  >
                    <Text fontSize="sm" fontWeight="semibold" mb={3} color="gray.700">
                      Audio Language Detection Results:
                    </Text>
                    
                    <Box
                      p={4}
                      bg="white"
                      borderRadius="md"
                      border="2px solid"
                      borderColor="orange.300"
                    >
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
                          <Box>
                            <Text fontSize="xs" color="gray.600" mb={1}>
                              Confidence Score
                            </Text>
                            <HStack spacing={2} align="center">
                              <Text fontSize="lg" fontWeight="semibold" color="gray.800">
                                {(conf * 100).toFixed(2)}%
                              </Text>
                              <Box
                                flex={1}
                                h="8px"
                                bg="gray.200"
                                borderRadius="full"
                                overflow="hidden"
                              >
                                <Box
                                  h="100%"
                                  bg="orange.500"
                                  w={`${conf * 100}%`}
                                  transition="width 0.3s"
                                />
                              </Box>
                            </HStack>
                          </Box>
                        )}
                      </VStack>
                    </Box>
                  </Box>
                );
              })()}

              {fetched && (
                <Button
                  onClick={clearResults}
                  variant="outline"
                  size="sm"
                  w="full"
                >
                  Clear Results
                </Button>
              )}
            </VStack>
          </GridItem>
        </Grid>
      </ContentLayout>
    </>
  );
};

export default AudioLanguageDetectionPage;
