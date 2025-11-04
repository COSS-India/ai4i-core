// LLM service testing page with language selection and text processing

import React from 'react';
import Head from 'next/head';
import {
  Grid,
  GridItem,
  Heading,
  Text,
  Progress,
  VStack,
  Box,
  useToast,
} from '@chakra-ui/react';
import { useQuery } from '@tanstack/react-query';
import { useLLM } from '../hooks/useLLM';
import { listLLMModels } from '../services/llmService';
import { SUPPORTED_LANGUAGES } from '../config/constants';
import ContentLayout from '../components/common/ContentLayout';
import LanguageSelector from '../components/llm/LanguageSelector';
import TextInput from '../components/llm/TextInput';
import LLMResults from '../components/llm/LLMResults';
import DualComparison from '../components/llm/DualComparison';
import LoadingSpinner from '../components/common/LoadingSpinner';

const LLMPage: React.FC = () => {
  const toast = useToast();
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
  } = useLLM();

  // Fetch available LLM models
  const { data: models, isLoading: modelsLoading } = useQuery({
    queryKey: ['llm-models'],
    queryFn: listLLMModels,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const availableLanguages = SUPPORTED_LANGUAGES.map(lang => lang.code);

  const handleProcess = () => {
    if (!inputText.trim()) {
      toast({
        title: 'Input Required',
        description: 'Please enter text to process.',
        status: 'warning',
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
        <title>LLM - GPT OSS 20B | AI4Inclusion Console</title>
        <meta name="description" content="Test GPT OSS 20B Large Language Model for text processing, translation, and generation" />
      </Head>

      <ContentLayout>
        <VStack spacing={6} w="full">
          {/* Page Header */}
          <Box textAlign="center" mb={2}>
            <Heading size="lg" color="gray.800" mb={1}>
              Large Language Model - GPT OSS 20B
            </Heading>
            <Text color="gray.600" fontSize="sm">
              Translate and generate text with GPT OSS 20B
            </Text>
          </Box>

          <Grid
            templateColumns={{ base: '1fr', lg: '1fr 1fr' }}
            gap={8}
            w="full"
            maxW="1200px"
            mx="auto"
          >
            {/* Configuration Panel */}
            <GridItem>
              <VStack spacing={6} align="stretch">
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
                  <Box p={4} bg="red.50" borderRadius="md" border="1px" borderColor="red.200">
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
                      Select input and output languages, then enter text to process.
                      The LLM will translate or generate text based on your configuration.
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

