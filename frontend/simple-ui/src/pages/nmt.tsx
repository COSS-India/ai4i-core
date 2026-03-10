// NMT service testing page with language pair selection and translation

import {
  Alert,
  AlertDescription,
  AlertIcon,
  AlertTitle,
  Box,
  Button,
  Grid,
  GridItem,
  Heading,
  HStack,
  Progress,
  Text,
  VStack,
} from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import Head from "next/head";
import { useRouter } from "next/router";
import React, { useEffect, useState } from "react";
import { FaLanguage } from "react-icons/fa";
import ContentLayout from "../components/common/ContentLayout";
import LoadingSpinner from "../components/common/LoadingSpinner";
import { getServiceDescription, getServiceTitle } from "../config/serviceMetadata";
import ModelLanguageSelector from "../components/nmt/ModelLanguageSelector";
import TextTranslator from "../components/nmt/TextTranslator";
import TranslationResults from "../components/nmt/TranslationResults";
import { useAuth } from "../hooks/useAuth";
import { useNMT } from "../hooks/useNMT";
import {
  getSupportedLanguagePairsForService,
  listNMTServices,
} from "../services/nmtService";
import { getRemainingTryItRequests, shouldWarnAboutRateLimit } from "../services/tryItService";
import { useToastWithDeduplication } from "../hooks/useToastWithDeduplication";

const NMTPage: React.FC = () => {
  const toast = useToastWithDeduplication();
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [showRateLimitWarning, setShowRateLimitWarning] = useState(false);
  const [remainingRequests, setRemainingRequests] = useState(5);
  
  const {
    languagePair,
    selectedServiceId,
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
    setSelectedServiceId,
    clearResults,
  } = useNMT();

  // Fetch available services (anonymous: try-it API with X-Try-It: true; logged-in: model management with auth)
  const { data: services, isLoading: servicesLoading } = useQuery({
    queryKey: ["nmt-services", isAuthenticated],
    queryFn: listNMTServices,
    staleTime: 10 * 60 * 1000, // 10 minutes
  });

  // Check if user is anonymous and update rate limit info
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      setShowRateLimitWarning(shouldWarnAboutRateLimit());
      setRemainingRequests(getRemainingTryItRequests());
    }
  }, [isAuthenticated, authLoading, fetched]);

  // Update remaining requests after each translation
  useEffect(() => {
    if (!isAuthenticated && fetched) {
      setRemainingRequests(getRemainingTryItRequests());
      setShowRateLimitWarning(shouldWarnAboutRateLimit());
    }
  }, [isAuthenticated, fetched]);

  // Fetch available language pairs for selected service
  const { data: languagePairs, isLoading: pairsLoading } = useQuery({
    queryKey: ["nmt-language-pairs", selectedServiceId],
    queryFn: () =>
      getSupportedLanguagePairsForService(selectedServiceId, services || []),
    enabled: !!selectedServiceId && !!services && services.length > 0,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const canTranslate =
    !!selectedServiceId?.trim() &&
    !!languagePair.sourceLanguage?.trim() &&
    !!languagePair.targetLanguage?.trim() &&
    languagePair.sourceLanguage !== languagePair.targetLanguage &&
    !!inputText?.trim();

  const handleTranslate = () => {
    if (!canTranslate) return;
    performInference(inputText);
  };

  return (
    <>
      <Head>
        <title>NMT - Neural Machine Translation | AI4Inclusion Console</title>
        <meta
          name="description"
          content="Test Neural Machine Translation across Indic languages"
        />
      </Head>

      <ContentLayout>
        <VStack spacing={8} w="full">
          {/* Page Header */}
          <Box textAlign="center">
            <Heading size="xl" color="gray.800" mb={2} userSelect="none" cursor="default" tabIndex={-1}>
              {getServiceTitle("nmt")}
            </Heading>
            <Text color="gray.600" fontSize="lg" userSelect="none" cursor="default">
              {getServiceDescription("nmt")}
            </Text>
          </Box>

          {/* Anonymous User Alert */}
          {!authLoading && !isAuthenticated && (
            <Alert
              status={showRateLimitWarning ? "warning" : "info"}
              variant="left-accent"
              borderRadius="md"
              maxW="1200px"
              w="full"
            >
              <AlertIcon />
              <Box flex="1">
                <AlertTitle>
                  {showRateLimitWarning
                    ? "Rate Limit Warning"
                    : "Try Neural Machine Translation"}
                </AlertTitle>
                <AlertDescription fontSize="sm">
                  {showRateLimitWarning ? (
                    <>
                      You have approximately <strong>{remainingRequests} translation{remainingRequests !== 1 ? 's' : ''}</strong> remaining.
                      Sign in to get unlimited access to all services.
                    </>
                  ) : (
                    <>
                      You&apos;re using NMT without an account. You can try up to{" "}
                      <strong>5 translations per hour</strong>. Sign in for unlimited access.
                    </>
                  )}
                </AlertDescription>
              </Box>
              
            </Alert>
          )}

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
                {/* Service and Language Selector - same layout for all users (anonymous can change service from try-it API list) */}
                <Box pt={0} mt={0}>
                  <ModelLanguageSelector
                    languagePair={languagePair}
                    onLanguagePairChange={setLanguagePair}
                    availableLanguagePairs={languagePairs || []}
                    loading={pairsLoading || servicesLoading}
                    selectedServiceId={selectedServiceId}
                    onServiceChange={setSelectedServiceId}
                    hideServiceSelector={false}
                  />
                </Box>

                {/* Source Text */}
                <Box>
                  <TextTranslator
                    inputText={inputText}
                    onInputChange={setInputText}
                    maxLength={512}
                    disabled={fetching}
                  />
                </Box>

                {/* Instruction above Translate (same order as TTS/ASR) */}
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

            {/* Results Panel - translation output on right, aligned with left */}
            <GridItem pt={0} mt={0} alignSelf="flex-start">
              <VStack spacing={6} align="stretch" pt={0} mt={0}>
                {fetching && (
                  <Box>
                    <Text mb={2} fontSize="sm" color="gray.600">
                      Translating text...
                    </Text>
                    <Progress size="xs" isIndeterminate colorScheme="orange" />
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

                {fetched && translatedText && (
                  <>
                    <Box
                      p={4}
                      bg="gray.50"
                      borderRadius="md"
                      borderWidth="1px"
                      borderColor="gray.200"
                      w="full"
                    >
                      <Text fontSize="sm" fontWeight="semibold" color="gray.700" mb={2}>
                        Translation
                      </Text>
                      <Text fontSize="sm" color="gray.800" whiteSpace="pre-wrap">
                        {translatedText}
                      </Text>
                    </Box>
                    <TranslationResults
                      sourceText={inputText}
                      translatedText={translatedText}
                      requestWordCount={requestWordCount}
                      responseWordCount={responseWordCount}
                      responseTime={Number(requestTime)}
                    />
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

export default NMTPage;
