// NMT service testing page — uses reusable service page architecture

import { Alert, AlertDescription, AlertIcon, AlertTitle, Box, Button } from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/router";
import React, { useEffect, useMemo, useState } from "react";
import { FaLanguage } from "react-icons/fa";
import ModelLanguageSelector from "../components/nmt/ModelLanguageSelector";
import {
  buildResponseMetadata,
  RequestContainer,
  ResponseContainer,
  ServicePageLayout,
  useCopyToClipboard,
} from "../components/service-page";
import { getServicePageDefaults } from "../constants/servicePageConfig";
import { useAuth } from "../hooks/useAuth";
import { useNMT } from "../hooks/useNMT";
import {
  getSupportedLanguagePairsForService,
  listNMTServices,
} from "../services/nmtService";
import { getRemainingTryItRequests, shouldWarnAboutRateLimit } from "../services/tryItService";
import { TRY_IT_REQUESTS_PER_HOUR } from "../constants/limits";

const pageDefaults = getServicePageDefaults("nmt");

const NMTPage: React.FC = () => {
  const router = useRouter();
  const { copy } = useCopyToClipboard();
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

  const {
    data: services,
    isLoading: servicesLoading,
    isError: servicesError,
    error: servicesLoadError,
  } = useQuery({
    queryKey: ["nmt-services", isAuthenticated],
    queryFn: listNMTServices,
    enabled: !authLoading,
    staleTime: 10 * 60 * 1000,
    retry: 1,
  });

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      setShowRateLimitWarning(shouldWarnAboutRateLimit());
      setRemainingRequests(getRemainingTryItRequests());
    }
  }, [isAuthenticated, authLoading, fetched]);

  useEffect(() => {
    if (!isAuthenticated && fetched) {
      setRemainingRequests(getRemainingTryItRequests());
      setShowRateLimitWarning(shouldWarnAboutRateLimit());
    }
  }, [isAuthenticated, fetched]);

  const { data: languagePairs, isLoading: pairsLoading } = useQuery({
    queryKey: ["nmt-language-pairs", selectedServiceId],
    queryFn: () =>
      getSupportedLanguagePairsForService(selectedServiceId, services || []),
    enabled: !!selectedServiceId && !!services && services.length > 0,
    staleTime: 5 * 60 * 1000,
  });

  const anonymousRateLimitReached =
    !authLoading && !isAuthenticated && remainingRequests <= 0;

  const canTranslate =
    !!selectedServiceId?.trim() &&
    !!languagePair.sourceLanguage?.trim() &&
    !!languagePair.targetLanguage?.trim() &&
    languagePair.sourceLanguage !== languagePair.targetLanguage &&
    !!inputText?.trim() &&
    !anonymousRateLimitReached;

  const responseMetadata = useMemo(
    () =>
      buildResponseMetadata({
        requestWordCount,
        responseWordCount,
        responseTimeMs: Number(requestTime),
      }),
    [requestWordCount, responseWordCount, requestTime]
  );

  const rateLimitBanner = !authLoading && !isAuthenticated && (
    <Alert
      status={
        anonymousRateLimitReached ? "error" : showRateLimitWarning ? "warning" : "info"
      }
      variant="left-accent"
      borderRadius="md"
      w="full"
      maxW="1200px"
      mx="auto"
    >
      <AlertIcon />
      <Box flex="1">
        <AlertTitle fontSize="md">
          {anonymousRateLimitReached
            ? "Rate Limit Reached"
            : showRateLimitWarning
              ? "Rate Limit Warning"
              : "Try Neural Machine Translation"}
        </AlertTitle>
        <AlertDescription fontSize="sm">
          {anonymousRateLimitReached ? (
            <>
              You have used all <strong>{TRY_IT_REQUESTS_PER_HOUR} translations</strong> for this hour.
              Sign in to get access to all services, or try again later.
            </>
          ) : showRateLimitWarning ? (
            <>
              You have approximately{" "}
              <strong>
                {remainingRequests} translation{remainingRequests !== 1 ? "s" : ""}
              </strong>{" "}
              remaining. Sign in to get access to all services.
            </>
          ) : (
            <>
              You&apos;re using NMT without an account. You can try up to{" "}
              <strong>{TRY_IT_REQUESTS_PER_HOUR} translations per hour</strong>. Sign in to get access to all
              services.
            </>
          )}
        </AlertDescription>
      </Box>
      {!anonymousRateLimitReached && (
        <Button
          size="sm"
          colorScheme="orange"
          variant="outline"
          onClick={() => router.push("/auth")}
        >
          Sign In
        </Button>
      )}
    </Alert>
  );

  return (
    <ServicePageLayout
      serviceId="nmt"
      headDescription="Test Neural Machine Translation across Indic languages"
      banner={rateLimitBanner}
      requestPanel={
        <RequestContainer
          inputType="text"
          topSlot={
            servicesError ? (
              <Alert status="error" borderRadius="md">
                <AlertIcon />
                <AlertDescription fontSize="sm">
                  Could not load NMT services.{" "}
                  {servicesLoadError instanceof Error
                    ? servicesLoadError.message
                    : "Please refresh the page or try again later."}
                </AlertDescription>
              </Alert>
            ) : undefined
          }
          textInput={{
            value: inputText,
            onChange: setInputText,
            placeholder: pageDefaults.textPlaceholder,
            maxLength: pageDefaults.maxTextLength,
            disabled: fetching || !selectedServiceId,
          }}
          helperText={pageDefaults.helperText}
          submitButton={{
            label: pageDefaults.submitLabel,
            loadingLabel: pageDefaults.submitLoadingLabel,
            onClick: () => canTranslate && performInference(inputText),
            isLoading: fetching,
            isDisabled: !canTranslate || fetching,
            icon: <FaLanguage />,
          }}
        >
          <ModelLanguageSelector
            languagePair={languagePair}
            onLanguagePairChange={setLanguagePair}
            availableLanguagePairs={languagePairs || []}
            loading={pairsLoading || servicesLoading}
            selectedServiceId={selectedServiceId}
            onServiceChange={setSelectedServiceId}
            hideServiceSelector={false}
            inferenceInProgress={fetching}
          />
        </RequestContainer>
      }
      responsePanel={
        <ResponseContainer
          fetching={fetching}
          fetchingLabel="Translating text..."
          error={error}
          fetched={fetched}
          hasResult={!!translatedText}
          resultTitle="Translation"
          resultContent={translatedText}
          metadata={fetched && translatedText ? responseMetadata : []}
          actions={
            fetched && translatedText
              ? [
                  {
                    id: "copy-source",
                    label: "Copy Source",
                    kind: "copy",
                    onClick: () => copy(inputText, "Source text copied to clipboard."),
                  },
                  {
                    id: "copy-translation",
                    label: "Copy Translation",
                    kind: "copy",
                    onClick: () => copy(translatedText, "Translation copied to clipboard."),
                  },
                ]
              : []
          }
          onClear={clearResults}
        />
      }
    />
  );
};

export default NMTPage;
