// NMT service testing page with language pair selection and translation

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
import { useNMT } from '../hooks/useNMT';
import { getSupportedLanguagePairs } from '../services/nmtService';
import ContentLayout from '../components/common/ContentLayout';
import LanguageSelector from '../components/nmt/LanguageSelector';
import TextTranslator from '../components/nmt/TextTranslator';
import TranslationResults from '../components/nmt/TranslationResults';
import LoadingSpinner from '../components/common/LoadingSpinner';

const NMTPage: React.FC = () => {
  const toast = useToast();
  const {
    languagePair,
    inputText,
    translatedText,
    fetching,
    fetched,
    requestWordCount,
    responseWordCount,
    requestTime,
    error,
    performInference,
    setInputText,
    setLanguagePair,
    clearResults,
    swapLanguages,
  } = useNMT();

  // Fetch available language pairs
  const { data: languagePairs, isLoading: pairsLoading } = useQuery({
    queryKey: ['nmt-language-pairs'],
    queryFn: getSupportedLanguagePairs,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const handleTranslate = () => {
    if (!inputText.trim()) {
      toast({
        title: 'Input Required',
        description: 'Please enter text to translate.',
        status: 'warning',
        duration: 3000,
        isClosable: true,
      });
      return;
    }
    performInference(inputText);
  };

  const handleSwapTexts = () => {
    swapLanguages();
  };

  return (
    <>
      <Head>
        <title>NMT - Neural Machine Translation | Simple UI</title>
        <meta name="description" content="Test Neural Machine Translation between 22+ Indian languages" />
      </Head>

      <ContentLayout>
        <VStack spacing={8} w="full">
          {/* Page Header */}
          <Box textAlign="center">
            <Heading size="xl" color="gray.800" mb={2}>
              Neural Machine Translation
            </Heading>
            <Text color="gray.600" fontSize="lg">
              Translate text between 22+ Indian languages with high accuracy
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
                {/* Language Pair Selector */}
                <Box>
                  <Text className="dview-service-try-option-title" mb={4}>
                    Language Configuration
                  </Text>
                  <LanguageSelector
                    languagePair={languagePair}
                    onLanguagePairChange={setLanguagePair}
                    availableLanguagePairs={languagePairs || []}
                    loading={pairsLoading}
                  />
                </Box>

                {/* Text Translator */}
                <Box>
                  <TextTranslator
                    inputText={inputText}
                    translatedText={translatedText}
                    onInputChange={setInputText}
                    onTranslate={handleTranslate}
                    isLoading={fetching}
                    sourceLanguage={languagePair.sourceLanguage}
                    maxLength={512}
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
                      Translating text...
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

                {/* Translation Results */}
                {fetched && translatedText && (
                  <TranslationResults
                    sourceText={inputText}
                    translatedText={translatedText}
                    requestWordCount={requestWordCount}
                    responseWordCount={responseWordCount}
                    responseTime={Number(requestTime)}
                    onSwapTexts={handleSwapTexts}
                  />
                )}

                {/* Clear Results Button */}
                {fetched && (
                  <Box textAlign="center">
                    <button
                      onClick={clearResults}
                      style={{
                        padding: '8px 16px',
                        backgroundColor: '#f7fafc',
                        border: '1px solid #e2e8f0',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        fontSize: '14px',
                        color: '#4a5568',
                      }}
                    >
                      Clear Results
                    </button>
                  </Box>
                )}

                {/* Instructions */}
                {!fetched && !fetching && (
                  <Box p={6} bg="gray.50" borderRadius="md" textAlign="center">
                    <Text color="gray.600" fontSize="sm">
                      Select a language pair and enter text to translate.
                      The system supports translation between 22+ Indian languages.
                    </Text>
                  </Box>
                )}
              </VStack>
            </GridItem>
          </Grid>

          {/* Language Pairs Loading Indicator */}
          {pairsLoading && (
            <Box textAlign="center">
              <LoadingSpinner label="Loading language pairs..." />
            </Box>
          )}
        </VStack>
      </ContentLayout>
    </>
  );
};

export default NMTPage;