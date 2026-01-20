// LLM service testing page with language selection and text processing

import {
  Box,
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
import ContentLayout from "../components/common/ContentLayout";
import LoadingSpinner from "../components/common/LoadingSpinner";
import DualComparison from "../components/llm/DualComparison";
import LanguageSelector from "../components/llm/LanguageSelector";
import TextInput from "../components/llm/TextInput";
import { LLM_SUPPORTED_LANGUAGES } from "../config/constants";
import { useLLM } from "../hooks/useLLM";
import { listLLMModels, listLLMServices } from "../services/llmService";

const LLMPage: React.FC = () => {
  const toast = useToast();
  const [serviceId, setServiceId] = useState<string>("");
  const {
    selectedModelId,
    inputLanguage,
    outputLanguage,
    inputText,
    outputText,
    nmtOutputText,
    fetching,
    fetched,
    isDualMode,
    requestWordCount,
    responseWordCount,
    nmtResponseWordCount,
    requestTime,
    nmtRequestTime,
    error,
    performDualInference,
    setInputText,
    setInputLanguage,
    setOutputLanguage,
    setSelectedModelId,
    clearResults,
    swapLanguages,
  } = useLLM(serviceId);

  // Fetch available LLM services
  const { data: llmServices, isLoading: servicesLoading } = useQuery({
    queryKey: ["llm-services"],
    queryFn: listLLMServices,
    staleTime: 10 * 60 * 1000, // 10 minutes
  });

  // Fetch available LLM models
  const { data: models, isLoading: modelsLoading } = useQuery({
    queryKey: ["llm-models"],
    queryFn: listLLMModels,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  // Auto-select first available LLM service when list loads
  useEffect(() => {
    if (!llmServices || llmServices.length === 0) return;
    if (!serviceId) {
      // If no service selected, select first available
      setServiceId(llmServices[0].service_id);
    }
  }, [llmServices, serviceId]);

  const availableLanguages = LLM_SUPPORTED_LANGUAGES.map((lang) => lang.code);

  const handleProcess = () => {
    if (!inputText.trim()) {
      toast({
        title: "Input Required",
        description: "Please enter text to process.",
        status: "warning",
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    // Always use dual translation (LLM + NMT)
    performDualInference(inputText);
  };

  const handleSwapTexts = () => {
    swapLanguages();
  };

  return (
    <>
      <Head>
        <title>LLM | AI4Inclusion Console</title>
        <meta
          name="description"
          content="Test Large Language Model for text processing, translation, and generation"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={6} w="full">
          {/* Page Header */}
          <Box textAlign="center" mb={2}>
            <Heading size="lg" color="gray.800" mb={1}>
              Large Language Model
            </Heading>
            <Text color="gray.600" fontSize="sm">
              Translate and generate text
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
                    LLM Service:
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
                      placeholder="Select an LLM service"
                      disabled={fetching}
                      size="md"
                      borderColor="gray.300"
                      _focus={{
                        borderColor: "orange.400",
                        boxShadow: "0 0 0 1px var(--chakra-colors-orange-400)",
                      }}
                    >
                      {llmServices?.map((service) => (
                        <option key={service.service_id} value={service.service_id}>
                          {service.name || service.service_id} {service.model_version ? `(${service.model_version})` : ''}
                        </option>
                      ))}
                    </Select>
                  )}
                  {serviceId && llmServices && (
                    <Box mt={2} p={3} bg="orange.50" borderRadius="md" border="1px" borderColor="orange.200">
                      {(() => {
                        const selectedService = llmServices.find(s => s.service_id === serviceId);
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

                {/* Language Selector */}
                <Box>
                  <LanguageSelector
                    inputLanguage={inputLanguage}
                    outputLanguage={outputLanguage}
                    onInputLanguageChange={setInputLanguage}
                    onOutputLanguageChange={setOutputLanguage}
                    availableLanguages={availableLanguages}
                  />
                </Box>

                {/* Text Input */}
                <Box>
                  <TextInput
                    inputText={inputText}
                    onInputChange={setInputText}
                    onProcess={handleProcess}
                    isLoading={fetching}
                    inputLanguage={inputLanguage}
                    maxLength={50000}
                    disabled={fetching}
                  />
                </Box>
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

                {/* Dual Comparison Results - Always show dual mode */}
                {fetched && nmtOutputText && (
                  <DualComparison
                    sourceText={inputText}
                    llmOutput={outputText}
                    nmtOutput={nmtOutputText}
                    requestWordCount={requestWordCount}
                    llmResponseWordCount={responseWordCount}
                    nmtResponseWordCount={nmtResponseWordCount || 0}
                    llmResponseTime={Number(requestTime)}
                    nmtResponseTime={Number(nmtRequestTime || 0)}
                  />
                )}

                {/* Instructions */}
                {!fetched && !fetching && (
                  <Box p={6} bg="gray.50" borderRadius="md" textAlign="center">
                    <Text color="gray.600" fontSize="sm">
                      Select input and output languages, then enter text to
                      process. The LLM will translate or generate text based on
                      your configuration.
                    </Text>
                  </Box>
                )}
              </VStack>
            </GridItem>
          </Grid>

          {/* Models Loading Indicator */}
          {modelsLoading && (
            <Box textAlign="center">
              <LoadingSpinner label="Loading LLM models..." />
            </Box>
          )}
        </VStack>
      </ContentLayout>
    </>
  );
};

export default LLMPage;
