// LLM service testing page with language selection and text processing

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
import { FaLanguage } from "react-icons/fa";
import { useQuery } from "@tanstack/react-query";
import Head from "next/head";
import React, { useState, useEffect } from "react";
import ContentLayout from "../components/common/ContentLayout";
import LoadingSpinner from "../components/common/LoadingSpinner";
import DualComparison from "../components/llm/DualComparison";
import LanguageSelector from "../components/llm/LanguageSelector";
import TextInput from "../components/llm/TextInput";
import { LLM_SUPPORTED_LANGUAGES } from "../config/constants";
import { getServiceDescription, getServiceTitle } from "../config/serviceMetadata";
import { useLLM } from "../hooks/useLLM";
import { listLLMModels, listLLMServices } from "../services/llmService";
import { useToastWithDeduplication } from "../hooks/useToastWithDeduplication";

const LLMPage: React.FC = () => {
  const toast = useToastWithDeduplication();
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

  const availableLanguages = LLM_SUPPORTED_LANGUAGES.map((lang) => lang.code);

  const MAX_LLM_INPUT_LENGTH = 512;
  const canTranslate =
    !!serviceId?.trim() &&
    !!inputLanguage?.trim() &&
    !!outputLanguage?.trim() &&
    inputLanguage !== outputLanguage &&
    !!inputText?.trim() &&
    inputText.length <= MAX_LLM_INPUT_LENGTH;

  const handleTranslate = () => {
    if (!canTranslate) return;
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
            <Heading size="lg" color="gray.800" mb={1} userSelect="none" cursor="default" tabIndex={-1}>
              {getServiceTitle("llm")}
            </Heading>
            <Text color="gray.600" fontSize="sm" userSelect="none" cursor="default">
              {getServiceDescription("llm")}
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
                    LLM Service{" "}
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
                      {llmServices?.map((service) => (
                        <option key={service.service_id} value={service.service_id}>
                          {service.name || service.service_id} {service.model_version ? `(${service.model_version})` : ''}
                        </option>
                      ))}
                    </Select>
                  )}
                  {serviceId && llmServices && (
                    <Box
                      mt={2}
                      p={3}
                      bg="orange.50"
                      borderRadius="md"
                      border="1px"
                      borderColor="orange.200"
                    >
                      {(() => {
                        const selectedService = llmServices.find(
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

                {/* Language Configuration */}
                <Box>
                  <Text className="dview-service-try-option-title" mb={4}>
                    Language Configuration
                  </Text>
                  <LanguageSelector
                    inputLanguage={inputLanguage}
                    outputLanguage={outputLanguage}
                    onInputLanguageChange={setInputLanguage}
                    onOutputLanguageChange={setOutputLanguage}
                    availableLanguages={availableLanguages}
                    disabled={fetching || !serviceId}
                  />
                </Box>

                {/* Text Input */}
                <Box>
                  <TextInput
                    inputText={inputText}
                    onInputChange={setInputText}
                    maxLength={MAX_LLM_INPUT_LENGTH}
                    disabled={fetching || !serviceId}
                  />
                </Box>

                {/* Instruction above Translate (aligned with NMT) */}
                <Text fontSize="sm" color="gray.600">
                  Enter text and click &quot;Translate&quot; to translate. You can change source and target languages in the configuration above.
                </Text>

                {/* Translate Button */}
                <Button
                  leftIcon={<FaLanguage />}
                  colorScheme="orange"
                  size="lg"
                  onClick={handleTranslate}
                  isLoading={fetching}
                  loadingText="Translating..."
                  isDisabled={!canTranslate || fetching}
                  w="full"
                >
                  Translate
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
              </VStack>
            </GridItem>
          </Grid>
        </VStack>
      </ContentLayout>
    </>
  );
};

export default LLMPage;
