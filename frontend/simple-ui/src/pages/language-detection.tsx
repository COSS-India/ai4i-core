// Language Detection service testing page

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
  Text,
  Textarea,
  useToast,
  VStack,
} from "@chakra-ui/react";
import Head from "next/head";
import React, { useState } from "react";
import ContentLayout from "../components/common/ContentLayout";
import { performLanguageDetectionInference } from "../services/languageDetectionService";

const LanguageDetectionPage: React.FC = () => {
  const toast = useToast();
  const [inputTexts, setInputTexts] = useState("");
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [responseTime, setResponseTime] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  const handleProcess = async () => {
    if (!inputTexts.trim()) {
      toast({
        title: "Input Required",
        description: "Please enter text to detect language.",
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
      // Split by newlines or commas for multiple texts
      const texts = inputTexts
        .split(/[\n,]/)
        .map((t) => t.trim())
        .filter((t) => t.length > 0);

      const startTime = Date.now();
      const response = await performLanguageDetectionInference(
        texts,
        "ai4bharat/indiclid"
      );
      const endTime = Date.now();
      const calculatedTime = ((endTime - startTime) / 1000).toFixed(2);

      setResult(response.data);
      setResponseTime(parseFloat(calculatedTime));
      setFetched(true);
    } catch (err: any) {
      // Prioritize API error message from response
      let errorMessage = "Failed to perform language detection";
      
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
    setInputTexts("");
    setError(null);
  };

  const wordCount = inputTexts.trim() ? inputTexts.trim().split(/\s+/).length : 0;

  return (
    <>
      <Head>
        <title>Language Detection | AI4Inclusion Console</title>
        <meta
          name="description"
          content="Test Language Detection to identify text language and script"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={8} w="full">
          {/* Page Header */}
          <Box textAlign="center">
            <Heading size="xl" color="gray.800" mb={2}>
              Text Language Detection
            </Heading>
            <Text color="gray.600" fontSize="lg">
              A lightweight language identification service for detecting the language of input text across multiple Indian languages.
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

              <FormControl>
                <FormLabel fontSize="sm" fontWeight="semibold">
                  Enter text to detect language:
                </FormLabel>
                <Textarea
                  value={inputTexts}
                  onChange={(e) => setInputTexts(e.target.value)}
                  placeholder="Enter text to detect language..."
                  rows={6}
                  isDisabled={fetching}
                  bg="white"
                  borderColor="gray.300"
                />
              </FormControl>

              {/* Metrics Box */}
              {(fetched || inputTexts.trim()) && (
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
                        Word Count
                      </Text>
                      <Text fontSize="lg" fontWeight="bold" color="gray.800">
                        {wordCount}
                      </Text>
                    </VStack>
                    {fetched && (
                      <VStack align="start" spacing={0}>
                        <Text fontSize="xs" color="gray.600">
                          Response Time
                        </Text>
                        <Text fontSize="lg" fontWeight="bold" color="gray.800">
                          {responseTime.toFixed(2)} seconds
                        </Text>
                      </VStack>
                    )}
                  </HStack>
                </Box>
              )}

                <Button
                  colorScheme="orange"
                  onClick={handleProcess}
                  isLoading={fetching}
                  loadingText="Processing..."
                  size="md"
                  w="full"
                >
                  Detect Language
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
                    Processing text...
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
                {(fetched || inputTexts.trim()) && (
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
                          Word Count
                        </Text>
                        <Text fontSize="lg" fontWeight="bold" color="gray.800">
                          {wordCount}
                        </Text>
                      </VStack>
                      {fetched && (
                        <VStack align="start" spacing={0}>
                          <Text fontSize="xs" color="gray.600">
                            Response Time
                          </Text>
                          <Text fontSize="lg" fontWeight="bold" color="gray.800">
                            {responseTime.toFixed(2)} seconds
                          </Text>
                        </VStack>
                      )}
                    </HStack>
                  </Box>
                )}

                {/* Language Detection Results */}
              {fetched && result && result.output && result.output.length > 0 && (
                  <>
                <Box
                  p={4}
                  bg="blue.50"
                  borderRadius="md"
                  border="1px"
                  borderColor="blue.200"
                >
                  <Text fontSize="sm" fontWeight="semibold" mb={2} color="gray.700">
                    Detected Language:
                  </Text>
                  {result.output.map((item: any, index: number) => {
                    // Support both new (langPrediction[]) and legacy (detectedLanguage/detectedScript) response shapes
                    const prediction =
                      Array.isArray(item.langPrediction) && item.langPrediction.length > 0
                        ? item.langPrediction[0]
                        : null;

                    let detectedLanguage = "Unknown";
                    let detectedScript: string | undefined;
                    let langCode: string | undefined;
                    let confidence: number | undefined;

                    if (prediction) {
                      detectedLanguage = prediction.language || "Unknown";
                      detectedScript = prediction.scriptCode;
                      langCode = prediction.langCode;
                      confidence = prediction.langScore;
                    } else {
                      // Fallback to legacy/alternate fields if present
                      detectedLanguage =
                        item.detectedLanguage ||
                        item.language ||
                        "Unknown";
                      detectedScript =
                        item.detectedScript ||
                        item.scriptCode ||
                        item.script;
                      langCode = item.langCode;
                      confidence = item.langScore;
                    }

                    return (
                      <Box key={index} mb={index < result.output.length - 1 ? 3 : 0}>
                        {item.source && (
                          <Text fontSize="xs" color="gray.600" mb={1}>
                            Text: {item.source}
                          </Text>
                        )}
                        <VStack align="start" spacing={1}>
                          <Text fontSize="md" fontWeight="semibold" color="blue.700">
                            {detectedLanguage}
                            {detectedScript && ` (${detectedScript} script)`}
                          </Text>
                          {langCode && (
                            <Text fontSize="xs" color="gray.500">
                              Code: {langCode}
                              {confidence !== undefined &&
                                ` • Confidence: ${(confidence * 100).toFixed(1)}%`}
                            </Text>
                          )}
                        </VStack>
                      </Box>
                    );
                  })}
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
              )}
            </VStack>
          </GridItem>
        </Grid>
        </VStack>
      </ContentLayout>
    </>
  );
};

export default LanguageDetectionPage;
