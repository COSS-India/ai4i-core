// Text Language Detection testing page

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
  Textarea,
  VStack,
} from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import Head from "next/head";
import React, { useState } from "react";
import ContentLayout from "../components/common/ContentLayout";
import { getServiceDescription, getServiceTitle } from "../config/serviceMetadata";
import { performLanguageDetectionInference, listLanguageDetectionServices } from "../services/languageDetectionService";
import { extractErrorInfo } from "../utils/errorHandler";
import { LANGUAGE_DETECTION_ERRORS, MIN_LANGUAGE_DETECTION_TEXT_LENGTH, MAX_TEXT_LENGTH, MAX_LANGUAGE_DETECTION_INPUT_LENGTH } from "../config/constants";
import { useToastWithDeduplication } from "../hooks/useToastWithDeduplication";

const LanguageDetectionPage: React.FC = () => {
  const toast = useToastWithDeduplication();
  const [serviceId, setServiceId] = useState<string>("");
  const [inputTexts, setInputTexts] = useState("");
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [responseTime, setResponseTime] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  const { data: languageDetectionServices, isLoading: servicesLoading } = useQuery({
    queryKey: ["language-detection-services"],
    queryFn: listLanguageDetectionServices,
    staleTime: 10 * 60 * 1000,
  });

  const canDetect =
    !!serviceId?.trim() &&
    !!inputTexts?.trim() &&
    inputTexts.length <= MAX_LANGUAGE_DETECTION_INPUT_LENGTH &&
    !fetching;

  const handleProcess = async () => {
    if (!serviceId?.trim()) {
      toast({
        title: "Service Required",
        description: "Please select a service before detecting language.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    const trimmedText = inputTexts.trim();
    if (!trimmedText) {
      const err = LANGUAGE_DETECTION_ERRORS.TEXT_REQUIRED;
      toast({
        title: err.title,
        description: err.description,
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    
    // Split by newlines or commas for multiple texts
    const texts = trimmedText
      .split(/[\n,]/)
      .map((t) => t.trim())
      .filter((t) => t.length > 0);
    
    // Validate that we have at least one valid text after splitting
    if (texts.length === 0) {
      const err = LANGUAGE_DETECTION_ERRORS.TEXT_REQUIRED;
      toast({
        title: err.title,
        description: err.description,
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    
    // Validate minimum text length for each text
    const tooShortTexts = texts.filter(t => t.length < MIN_LANGUAGE_DETECTION_TEXT_LENGTH);
    if (tooShortTexts.length > 0) {
      const err = LANGUAGE_DETECTION_ERRORS.TEXT_TOO_SHORT;
      toast({
        title: err.title,
        description: err.description,
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    
    // Validate total input length
    if (trimmedText.length > MAX_LANGUAGE_DETECTION_INPUT_LENGTH) {
      toast({
        title: "Input too long",
        description: `Total text must not exceed ${MAX_LANGUAGE_DETECTION_INPUT_LENGTH} characters.`,
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    // Validate maximum text length per segment
    const tooLongTexts = texts.filter(t => t.length > MAX_TEXT_LENGTH);
    if (tooLongTexts.length > 0) {
      const err = LANGUAGE_DETECTION_ERRORS.TEXT_TOO_LONG;
      toast({
        title: err.title,
        description: err.description,
        status: "error",
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
      const response = await performLanguageDetectionInference(
        texts,
        serviceId
      );
      const endTime = Date.now();
      const calculatedTime = ((endTime - startTime) / 1000).toFixed(2);

      setResult(response.data);
      setResponseTime(parseFloat(calculatedTime));
      setFetched(true);
    } catch (err: any) {
      // Use centralized error handler (language-detection context so backend message shown as default when no specific mapping)
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(err, 'language-detection');
      
      setError(errorMessage);
      toast({
        title: showOnlyMessage ? undefined : errorTitle,
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

  return (
    <>
      <Head>
        <title>Text Language Detection | AI4Inclusion Console</title>
        <meta
          name="description"
          content="Detect the language of any text input using Text Language Detection"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={8} w="full">
          {/* Page Header */}
          <Box textAlign="center">
            <Heading size="xl" color="gray.800" mb={2} userSelect="none" cursor="default" tabIndex={-1}>
              {getServiceTitle("language-detection")}
            </Heading>
            <Text color="gray.600" fontSize="lg" userSelect="none" cursor="default">
              {getServiceDescription("language-detection")}
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
              <FormControl>
                <FormLabel fontSize="sm" fontWeight="semibold">
                  Service <Text as="span" color="red.500">*</Text>
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
                    {languageDetectionServices?.map((service) => (
                      <option key={service.service_id} value={service.service_id}>
                        {service.name || service.service_id} {service.model_version ? `(${service.model_version})` : ''}
                      </option>
                    ))}
                  </Select>
                )}
                {serviceId && languageDetectionServices && (
                  <Box
                    mt={2}
                    p={3}
                    bg="orange.50"
                    borderRadius="md"
                    border="1px"
                    borderColor="orange.200"
                  >
                    {(() => {
                      const selectedService = languageDetectionServices.find(
                        (s) => s.service_id === serviceId
                      );
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

              <FormControl isInvalid={inputTexts.length > MAX_LANGUAGE_DETECTION_INPUT_LENGTH}>
                <FormLabel fontSize="sm" fontWeight="semibold">
                  Source Text <Text as="span" color="red.500">*</Text>
                </FormLabel>
                <Textarea
                  value={inputTexts}
                  onChange={(e) => setInputTexts(e.target.value)}
                  placeholder="Enter text to detect language..."
                  rows={6}
                  isDisabled={fetching}
                  bg="white"
                  maxLength={MAX_LANGUAGE_DETECTION_INPUT_LENGTH}
                  borderColor={inputTexts.length > MAX_LANGUAGE_DETECTION_INPUT_LENGTH ? "red.400" : "gray.300"}
                />
                {inputTexts.length > MAX_LANGUAGE_DETECTION_INPUT_LENGTH && (
                  <Text fontSize="sm" color="red.500" mt={1}>
                    Text exceeds the maximum limit of {MAX_LANGUAGE_DETECTION_INPUT_LENGTH} characters. Please reduce the length.
                  </Text>
                )}
              </FormControl>
              <Box display="flex" justifyContent="flex-end">
                <Text
                  fontSize="sm"
                  color={inputTexts.length > MAX_LANGUAGE_DETECTION_INPUT_LENGTH ? "red.500" : "gray.500"}
                  fontWeight={inputTexts.length > MAX_LANGUAGE_DETECTION_INPUT_LENGTH ? "semibold" : "normal"}
                >
                  {inputTexts.length} / {MAX_LANGUAGE_DETECTION_INPUT_LENGTH}
                </Text>
              </Box>

              <Text fontSize="sm" color="gray.600">
                Configure service and enter text, then click Detect Language.
              </Text>
              <Button
                colorScheme="orange"
                onClick={handleProcess}
                isLoading={fetching}
                loadingText="Processing..."
                size="md"
                w="full"
                isDisabled={!canDetect}
              >
                Detect Language
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
                        <VStack align="start" spacing={3}>
                          <Box>
                            <Text fontSize="xs" color="gray.600" mb={1}>
                              Language
                            </Text>
                            <Text fontSize="md" fontWeight="semibold" color="blue.700">
                              {detectedLanguage}
                              {detectedScript && ` (${detectedScript} script)`}
                              {langCode && ` (${langCode})`}
                            </Text>
                          </Box>
                          {confidence !== undefined && (
                            <Box w="full">
                              <Text fontSize="xs" color="gray.600" mb={1}>
                                Confidence Score
                              </Text>
                              <HStack spacing={2} align="center">
                                <Text fontSize="lg" fontWeight="semibold" color="gray.800">
                                  {(confidence * 100).toFixed(2)}%
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
                                    w={`${confidence * 100}%`}
                                    transition="width 0.3s"
                                  />
                                </Box>
                              </HStack>
                            </Box>
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
