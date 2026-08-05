// LLM service testing page — reusable service page architecture
// AI4IDS-2688: role-based LLM service visibility (Logged-in / Guest / Anonymous)

import {
  Alert,
  AlertDescription,
  AlertIcon,
  AlertTitle,
  Box,
  Button,
} from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/router";
import React, { useEffect, useMemo, useState } from "react";
import { FaLanguage } from "react-icons/fa";
import LLMResults from "../components/llm/LLMResults";
import {
  GuestUsageLimitBanner,
  mapToServiceOptions,
  RequestContainer,
  ResponseContainer,
  ServicePageLayout,
} from "../components/service-page";
import { LLM_SUPPORTED_LANGUAGES } from "../config/constants";
import { getServicePageDefaults } from "../config/servicePageConfig";
import { useAuth } from "../hooks/useAuth";
import { useGuestServices } from "../hooks/useGuestServices";
import { useLLM } from "../hooks/useLLM";
import { listLLMServices } from "../services/llmService";
import {
  ANONYMOUS_TRY_IT_REQUESTS_PER_HOUR,
  getRemainingTryItRequests,
  shouldWarnAboutRateLimit,
} from "../services/tryItService";

const pageDefaults = getServicePageDefaults("llm");

function resolveTargetsForSource(
  pairs: Array<{ source: string; target: string }>,
  flatTargets: string[],
  source: string
): string[] {
  const paired = source
    ? Array.from(new Set(pairs.filter((p) => p.source === source).map((p) => p.target)))
    : [];
  return paired.length > 0 ? paired : flatTargets;
}

const LLMPage: React.FC = () => {
  const router = useRouter();
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const { isGuest } = useGuestServices();
  const [serviceId, setServiceId] = useState<string>("");
  const [showRateLimitWarning, setShowRateLimitWarning] = useState(false);
  const [remainingRequests, setRemainingRequests] = useState(
    ANONYMOUS_TRY_IT_REQUESTS_PER_HOUR
  );

  const isAnonymous = !authLoading && !isAuthenticated;
  const getLanguageLabel = (code: string): string =>
    LLM_SUPPORTED_LANGUAGES.find((l) => l.code === code)?.label ?? code;

  const {
    data: services = [],
    isLoading: isLoadingServices,
    isError: servicesError,
  } = useQuery({
    queryKey: ["llm-services", isAuthenticated, isGuest],
    queryFn: listLLMServices,
    enabled: !authLoading,
    staleTime: 5 * 60 * 1000,
  });

  // AI4IDS-2688 / AI4IDS-2704: Anonymous list is already limited to one
  // (isTryItDefault, else lowest service_id) in listLLMServices.
  const visibleServices = services;

  useEffect(() => {
    if (visibleServices.length === 0) {
      setServiceId("");
      return;
    }
    const stillValid = visibleServices.some((s) => s.service_id === serviceId);
    if (!stillValid) {
      setServiceId(visibleServices[0].service_id);
    }
  }, [visibleServices, serviceId]);

  useEffect(() => {
    if (!isAnonymous) return;
    setShowRateLimitWarning(shouldWarnAboutRateLimit());
    setRemainingRequests(getRemainingTryItRequests());
  }, [isAnonymous, authLoading]);

  const selectedService = useMemo(
    () => visibleServices.find((s) => s.service_id === serviceId),
    [visibleServices, serviceId]
  );
  const modelName = selectedService?.name ?? "";
  const selectedServiceId = selectedService?.service_id ?? "";

  const selectedServiceHasNoLanguages =
    !!selectedService &&
    (selectedService.supported_source_languages.length === 0 ||
      selectedService.supported_target_languages.length === 0);

  const {
    inputLanguage,
    outputLanguage,
    inputText,
    outputText,
    fetching,
    fetched,
    requestWordCount,
    responseWordCount,
    requestTime,
    error,
    performInference,
    setInputText,
    setInputLanguage,
    setOutputLanguage,
    clearResults,
    swapLanguages,
  } = useLLM(selectedServiceId, modelName);

  useEffect(() => {
    if (!isAnonymous || !fetched) return;
    setRemainingRequests(getRemainingTryItRequests());
    setShowRateLimitWarning(shouldWarnAboutRateLimit());
  }, [isAnonymous, fetched]);

  const llmServiceOptions = useMemo(
    () => mapToServiceOptions(visibleServices),
    [visibleServices]
  );

  const sourceLanguageOptions = useMemo(
    () =>
      (selectedService?.supported_source_languages ?? []).map((code) => ({
        code,
        label: getLanguageLabel(code),
      })),
    [selectedService]
  );
  const targetLanguageOptions = useMemo(() => {
    const pairs = selectedService?.language_pairs ?? [];
    const flatTargets = selectedService?.supported_target_languages ?? [];
    const codes = resolveTargetsForSource(pairs, flatTargets, inputLanguage);
    return codes.map((code) => ({ code, label: getLanguageLabel(code) }));
  }, [selectedService, inputLanguage]);

  const sourceCodes = useMemo(
    () => new Set(sourceLanguageOptions.map((o) => o.code)),
    [sourceLanguageOptions]
  );
  const targetCodes = useMemo(
    () => new Set(targetLanguageOptions.map((o) => o.code)),
    [targetLanguageOptions]
  );

  useEffect(() => {
    if (inputLanguage && !sourceCodes.has(inputLanguage)) setInputLanguage("");
    if (outputLanguage && !targetCodes.has(outputLanguage)) setOutputLanguage("");
  }, [
    sourceCodes,
    targetCodes,
    inputLanguage,
    outputLanguage,
    setInputLanguage,
    setOutputLanguage,
  ]);

  const canSwap = useMemo(() => {
    if (!sourceCodes.has(outputLanguage)) return false;
    const pairs = selectedService?.language_pairs ?? [];
    const flatTargets = selectedService?.supported_target_languages ?? [];
    const targetsFromSwappedSource = resolveTargetsForSource(pairs, flatTargets, outputLanguage);
    return targetsFromSwappedSource.includes(inputLanguage);
  }, [sourceCodes, selectedService, outputLanguage, inputLanguage]);

  const anonymousRateLimitReached =
    isAnonymous && remainingRequests <= 0;

  const MAX_LLM_INPUT_LENGTH = pageDefaults.maxTextLength ?? 512;
  const canTranslate =
    !!serviceId?.trim() &&
    !!modelName?.trim() &&
    !!inputLanguage?.trim() &&
    !!outputLanguage?.trim() &&
    inputLanguage !== outputLanguage &&
    !!inputText?.trim() &&
    inputText.length <= MAX_LLM_INPUT_LENGTH &&
    !anonymousRateLimitReached;

  const lockServiceDropdown = isAnonymous && visibleServices.length <= 1;

  const anonymousBanner = isAnonymous && (
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
              : "Try Large Language Model"}
        </AlertTitle>
        <AlertDescription fontSize="sm">
          {anonymousRateLimitReached ? (
            <>
              You have used all{" "}
              <strong>{ANONYMOUS_TRY_IT_REQUESTS_PER_HOUR} requests</strong> for this
              hour. Sign in for full access, or try again later.
            </>
          ) : showRateLimitWarning ? (
            <>
              You have approximately{" "}
              <strong>
                {remainingRequests} request{remainingRequests !== 1 ? "s" : ""}
              </strong>{" "}
              remaining. Sign in for unrestricted LLM access.
            </>
          ) : (
            <>
              You&apos;re using LLM without an account. One published LLM service is
              available, with up to{" "}
              <strong>{ANONYMOUS_TRY_IT_REQUESTS_PER_HOUR} requests per hour</strong>.
              Sign in or continue as Guest for all registry services.
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

  const pageBanner = isAnonymous
    ? anonymousBanner
    : isGuest
      ? <GuestUsageLimitBanner />
      : undefined;

  return (
    <ServicePageLayout
      serviceId="llm"
      headingSize="lg"
      headDescription="Test Large Language Model for text processing, translation, and generation"
      banner={pageBanner}
      requestPanel={
        <RequestContainer
          topSlot={
            selectedServiceHasNoLanguages ? (
              <Alert status="warning" borderRadius="md">
                <AlertIcon />
                <AlertDescription fontSize="sm">
                  This service has no source or target languages configured.
                </AlertDescription>
              </Alert>
            ) : undefined
          }
          serviceDropdown={{
            label: "LLM Service",
            value: serviceId,
            onChange: setServiceId,
            options: llmServiceOptions,
            loading: isLoadingServices,
            disabled: fetching || lockServiceDropdown,
            error: servicesError
              ? "Failed to load services. Please refresh the page."
              : null,
          }}
          languageConfig={{
            mode: "source-target",
            sourceLanguage: inputLanguage,
            targetLanguage: outputLanguage,
            onSourceChange: setInputLanguage,
            onTargetChange: setOutputLanguage,
            sourceOptions: sourceLanguageOptions,
            targetOptions: targetLanguageOptions,
            onSwap: swapLanguages,
            swapDisabled: !canSwap,
            disabled: fetching || !serviceId || anonymousRateLimitReached,
          }}
          inputType="text"
          textInput={{
            value: inputText,
            onChange: setInputText,
            maxLength: MAX_LLM_INPUT_LENGTH,
            disabled: fetching || !serviceId || anonymousRateLimitReached,
            placeholder: pageDefaults.textPlaceholder,
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
        />
      }
      responsePanel={
        <ResponseContainer
          fetching={fetching}
          fetchingLabel="Processing text..."
          error={error}
          fetched={fetched}
          hasResult={!!outputText}
          result={
            fetched && outputText ? (
              <LLMResults
                sourceText={inputText}
                outputText={outputText}
                requestWordCount={requestWordCount}
                responseWordCount={responseWordCount}
                responseTime={Number(requestTime)}
                onSwapTexts={canSwap ? swapLanguages : undefined}
              />
            ) : undefined
          }
          onClear={clearResults}
        />
      }
    />
  );
};

export default LLMPage;
