// Text Language Detection — reusable service page architecture

import { Badge, Box, HStack, Text, VStack } from "@chakra-ui/react";
import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  buildResponseMetadata,
  mapToServiceOptions,
  RequestContainer,
  ResponseContainer,
  ServicePageLayout,
} from "../components/service-page";
import {
  LANGUAGE_DETECTION_ERRORS,
  MAX_LANGUAGE_DETECTION_INPUT_LENGTH,
  MIN_LANGUAGE_DETECTION_TEXT_LENGTH,
} from "../config/constants";
import { getServicePageDefaults } from "../config/servicePageConfig";
import {
  listLanguageDetectionServices,
  performLanguageDetectionInference,
} from "../services/languageDetectionService";
import { parseLanguagePredictions } from "../types/inference";
import { parseError } from "../utils/errorHandler";
import { useToastWithDeduplication } from "../utils/toast";

const pageDefaults = getServicePageDefaults("language-detection");

const getPredictionColor = (idx: number) => {
  const colors = ["orange", "blue", "green", "purple", "pink", "teal", "cyan", "yellow"];
  return colors[idx % colors.length] || "gray";
};

const LanguageDetectionPage: React.FC = () => {
  const toast = useToastWithDeduplication();
  const [inputText, setInputText] = useState("");
  const [selectedServiceId, setSelectedServiceId] = useState<string>("");
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [result, setResult] = useState<{ output?: unknown[] } | null>(null);
  const [responseTime, setResponseTime] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  const {
    data: services = [],
    isLoading: isLoadingServices,
    isError: servicesError,
  } = useQuery({
    queryKey: ["languageDetectionServices"],
    queryFn: listLanguageDetectionServices,
    staleTime: 5 * 60 * 1000,
  });

  const serviceOptions = useMemo(() => mapToServiceOptions(services), [services]);

  const trimmedText = inputText.trim();
  const canDetect =
    !!selectedServiceId?.trim() &&
    trimmedText.length >= MIN_LANGUAGE_DETECTION_TEXT_LENGTH &&
    trimmedText.length <= MAX_LANGUAGE_DETECTION_INPUT_LENGTH &&
    !fetching;

  const handleProcess = async () => {
    const text = trimmedText;
    if (!text) {
      const err = LANGUAGE_DETECTION_ERRORS.TEXT_REQUIRED;
      toast({ title: err.title, description: err.description, status: "error", duration: 3000, isClosable: true });
      return;
    }
    if (text.length < MIN_LANGUAGE_DETECTION_TEXT_LENGTH) {
      const err = LANGUAGE_DETECTION_ERRORS.TEXT_TOO_SHORT;
      toast({ title: err.title, description: err.description, status: "error", duration: 3000, isClosable: true });
      return;
    }
    if (text.length > MAX_LANGUAGE_DETECTION_INPUT_LENGTH) {
      const err = LANGUAGE_DETECTION_ERRORS.TEXT_TOO_LONG;
      toast({ title: err.title, description: err.description, status: "error", duration: 3000, isClosable: true });
      return;
    }
    if (!selectedServiceId) {
      toast({ title: "No Service Selected", description: "Please select a language detection service.", status: "warning", duration: 3000, isClosable: true });
      return;
    }

    setFetching(true);
    setError(null);
    setFetched(false);
    try {
      const response = await performLanguageDetectionInference([text], selectedServiceId);
      setResult(response.data);
      setResponseTime(response.responseTime / 1000);
      setFetched(true);
    } catch (err: unknown) {
      const { message: errorMessage } = parseError(err, { service: "language-detection" });
      setError(errorMessage);
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

  const firstOutput = result?.output?.[0] as { langPrediction?: unknown } | undefined;
  const predictions = parseLanguagePredictions(firstOutput?.langPrediction);
  const sortedPredictions = [...predictions].sort((a, b) => (b.langScore ?? 0) - (a.langScore ?? 0));
  const hasPredictions = sortedPredictions.length > 0;

  return (
    <ServicePageLayout
      serviceId="language-detection"
      headTitle="Text Language Detection | AI4Inclusion Console"
      headDescription="Test Text Language Detection to identify the language and script of any text input."
      requestPanel={
        <RequestContainer
          serviceDropdown={{
            label: "Language Detection Service",
            value: selectedServiceId,
            onChange: setSelectedServiceId,
            options: serviceOptions,
            loading: isLoadingServices,
            disabled: fetching,
            error: servicesError ? "Failed to load services. Please refresh the page." : null,
          }}
          inputType="text"
          textInput={{
            value: inputText,
            onChange: setInputText,
            label: "Input Text",
            placeholder: "Paste text here (e.g., Hindi, Kannada, Telugu)...",
            maxLength: MAX_LANGUAGE_DETECTION_INPUT_LENGTH,
            disabled: fetching || !selectedServiceId,
          }}
          helperText={pageDefaults.helperText}
          submitButton={{
            label: pageDefaults.submitLabel,
            loadingLabel: pageDefaults.submitLoadingLabel,
            onClick: handleProcess,
            isLoading: fetching,
            isDisabled: !canDetect,
          }}
        />
      }
      responsePanel={
        <ResponseContainer
          fetching={fetching}
          fetchingLabel="Processing text..."
          error={error}
          fetched={fetched}
          hasResult={hasPredictions}
          metadata={
            fetched ? buildResponseMetadata({ responseTimeMs: responseTime * 1000 }) : []
          }
          result={
            fetched && result ? (
              <Box p={4} bg="gray.50" borderRadius="md" border="1px" borderColor="gray.200">
                <Text fontSize="sm" fontWeight="semibold" mb={3} color="gray.700">
                  Detected Languages:
                </Text>
                {hasPredictions ? (
                  <VStack align="stretch" spacing={3}>
                    {sortedPredictions.map((pred, idx) => {
                      const languageLabel = pred.language || pred.langCode || "Unknown";
                      return (
                        <Box key={`${languageLabel}-${idx}`} p={3} bg="white" borderRadius="md" border="1px" borderColor="gray.200">
                          <HStack justify="space-between" align="start">
                            <Badge colorScheme={getPredictionColor(idx)} variant="subtle">
                              {String(languageLabel).toUpperCase()}
                            </Badge>
                            <Text fontSize="xs" color="gray.500">
                              Score: {(pred.langScore ?? 0).toFixed(3)}
                            </Text>
                          </HStack>
                          <Text mt={1} fontSize="xs" color="gray.600">
                            Script: {pred.scriptCode ?? "N/A"}
                          </Text>
                        </Box>
                      );
                    })}
                  </VStack>
                ) : (
                  <Text fontSize="sm" color="gray.500" fontStyle="italic">
                    No language predictions returned for this input.
                  </Text>
                )}
              </Box>
            ) : undefined
          }
          onClear={clearResults}
        />
      }
    />
  );
};

export default LanguageDetectionPage;
