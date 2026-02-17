// Transliteration service testing page

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
import React, { useState, useEffect } from "react";
import ContentLayout from "../components/common/ContentLayout";
import { performTransliterationInference, listTransliterationServices } from "../services/transliterationService";
import { TRANSLITERATION_ERRORS, MIN_TRANSLITERATION_TEXT_LENGTH, MAX_TEXT_LENGTH } from "../config/constants";
import { extractErrorInfo } from "../utils/errorHandler";
import { useToastWithDeduplication } from "../hooks/useToastWithDeduplication";

const TransliterationPage: React.FC = () => {
  const toast = useToastWithDeduplication();
  const [serviceId, setServiceId] = useState<string>("");
  const [inputText, setInputText] = useState("");
  const [sourceLanguage, setSourceLanguage] = useState("en");
  const [targetLanguage, setTargetLanguage] = useState("hi");
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [responseTime, setResponseTime] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  // Fetch available Transliteration services
  const { data: transliterationServices, isLoading: servicesLoading } = useQuery({
    queryKey: ["transliteration-services"],
    queryFn: listTransliterationServices,
    staleTime: 10 * 60 * 1000, // 10 minutes
  });

  // Auto-select first available Transliteration service when list loads
  useEffect(() => {
    if (!transliterationServices || transliterationServices.length === 0) return;
    if (!serviceId) {
      // If no service selected, select first available
      setServiceId(transliterationServices[0].service_id);
    }
  }, [transliterationServices, serviceId]);

  const handleProcess = async () => {
    const trimmedText = inputText.trim();
    
    // Validate input text
    if (!trimmedText) {
      const err = TRANSLITERATION_ERRORS.TEXT_REQUIRED;
      toast({
        title: err.title,
        description: err.description,
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    
    if (trimmedText.length < MIN_TRANSLITERATION_TEXT_LENGTH) {
      const err = TRANSLITERATION_ERRORS.TEXT_TOO_SHORT;
      toast({
        title: err.title,
        description: err.description,
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    
    if (trimmedText.length > MAX_TEXT_LENGTH) {
      const err = TRANSLITERATION_ERRORS.TEXT_TOO_LONG;
      toast({
        title: err.title,
        description: err.description,
        status: "error",
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    if (!serviceId) {
      toast({
        title: "Service Required",
        description: "Please select a Transliteration service.",
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
      const response = await performTransliterationInference(trimmedText, {
        serviceId: serviceId,
        language: {
          sourceLanguage,
          targetLanguage,
        },
        isSentence: true,
        numSuggestions: 0,
      });
      const endTime = Date.now();
      const calculatedTime = ((endTime - startTime) / 1000).toFixed(2);

      setResult(response.data);
      setResponseTime(parseFloat(calculatedTime));
      setFetched(true);
    } catch (err: any) {
      // Use centralized error handler (transliteration context so backend message shown as default when no specific mapping)
      const { title: errorTitle, message: errorMessage, showOnlyMessage } = extractErrorInfo(err, 'transliteration');
      
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
    setInputText("");
    setError(null);
  };

  return (
    <>
      <Head>
        <title>Transliteration | AI4Inclusion Console</title>
        <meta
          name="description"
          content="Test Transliteration to convert text between scripts"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={8} w="full">
          {/* Page Header */}
          <Box textAlign="center">
            <Heading size="xl" color="gray.800" mb={2} userSelect="none" cursor="default" tabIndex={-1}>
              Transliteration Service
            </Heading>
            <Text color="gray.600" fontSize="lg" userSelect="none" cursor="default">
              Convert text from one script to another while keeping pronunciation intact
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
                    Transliteration Service:
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
                      placeholder="Select a Transliteration service"
                      disabled={fetching}
                      size="md"
                      borderColor="gray.300"
                      _focus={{
                        borderColor: "orange.400",
                        boxShadow: "0 0 0 1px var(--chakra-colors-orange-400)",
                      }}
                    >
                      {transliterationServices?.map((service) => (
                        <option key={service.service_id} value={service.service_id}>
                          {service.name || service.service_id} {service.model_version ? `(${service.model_version})` : ''}
                        </option>
                      ))}
                    </Select>
                  )}
                  {serviceId && transliterationServices && (
                    <Box mt={2} p={3} bg="orange.50" borderRadius="md" border="1px" borderColor="orange.200">
                      {(() => {
                        const selectedService = transliterationServices.find(s => s.service_id === serviceId);
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

              <HStack spacing={4}>
                <FormControl>
                  <FormLabel fontSize="sm" fontWeight="semibold">
                    Source Language:
                  </FormLabel>
                  <Select
                    value={sourceLanguage}
                    onChange={(e) => setSourceLanguage(e.target.value)}
                    isDisabled={fetching}
                    size="md"
                  >
                    <option value="en">English</option>
                    <option value="hi">Hindi</option>
                    <option value="ta">Tamil</option>
                    <option value="te">Telugu</option>
                    <option value="kn">Kannada</option>
                    <option value="ml">Malayalam</option>
                    <option value="mr">Marathi</option>
                    <option value="gu">Gujarati</option>
                    <option value="bn">Bengali</option>
                    <option value="pa">Punjabi</option>
                    <option value="or">Odia</option>
                    <option value="as">Assamese</option>
                  </Select>
                </FormControl>

                <FormControl>
                  <FormLabel fontSize="sm" fontWeight="semibold">
                    Target Language:
                  </FormLabel>
                  <Select
                    value={targetLanguage}
                    onChange={(e) => setTargetLanguage(e.target.value)}
                    isDisabled={fetching}
                    size="md"
                  >
                    <option value="en">English</option>
                    <option value="hi">Hindi</option>
                    <option value="ta">Tamil</option>
                    <option value="te">Telugu</option>
                    <option value="kn">Kannada</option>
                    <option value="ml">Malayalam</option>
                    <option value="mr">Marathi</option>
                    <option value="gu">Gujarati</option>
                    <option value="bn">Bengali</option>
                    <option value="pa">Punjabi</option>
                    <option value="or">Odia</option>
                    <option value="as">Assamese</option>
                  </Select>
                </FormControl>
              </HStack>

                <FormControl>
                  <FormLabel fontSize="sm" fontWeight="semibold">
                    Enter text to transliterate:
                  </FormLabel>
                  <Textarea
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    placeholder="Enter text to transliterate..."
                    rows={6}
                    isDisabled={fetching}
                    bg="white"
                    borderColor="gray.300"
                  />
                </FormControl>

                <Button
                  colorScheme="orange"
                  onClick={handleProcess}
                  isLoading={fetching}
                  loadingText="Processing..."
                  size="md"
                  w="full"
                >
                  Transliterate
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

                {/* Transliteration Results */}
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
                    Transliterated Text:
                  </Text>
                  {result.output.map((item: any, index: number) => (
                    <Box key={index}>
                      {item.source && (
                        <Text fontSize="xs" color="gray.600" mb={1}>
                          Source: {item.source}
                        </Text>
                      )}
                      <Text fontSize="md" fontWeight="semibold" color="blue.700">
                        {item.target}
                      </Text>
                    </Box>
                  ))}
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

export default TransliterationPage;
