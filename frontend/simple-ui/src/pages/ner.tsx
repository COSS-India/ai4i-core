// NER service testing page — reusable service page architecture

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
import { NER_ERRORS, MAX_TEXT_LENGTH, MIN_INFERENCE_TEXT_LENGTH, INDIC_LANGUAGE_OPTIONS } from '../constants';
import { getServicePageDefaults } from '../constants/servicePageConfig';
import { performNERInference, listNERServices } from "../services/nerService";
import { parseNerEntities } from "../types/inference";
import { parseError } from "../utils/errorHandler";
import { showToast } from "../utils/toast";

const pageDefaults = getServicePageDefaults("ner");

const getEntityColor = (label: string) => {
  const colors: Record<string, string> = {
    ORG: "orange",
    LOC: "blue",
    PER: "green",
    MISC: "purple",
    O: "gray",
  };
  return colors[label] || "gray";
};

const NERPage: React.FC = () => {
  const [inputText, setInputText] = useState("");
  const [sourceLanguage, setSourceLanguage] = useState("");
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [result, setResult] = useState<unknown>(null);
  const [responseTime, setResponseTime] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [selectedServiceId, setSelectedServiceId] = useState<string>("");

  const {
    data: services = [],
    isLoading: isLoadingServices,
    isError: servicesError,
  } = useQuery({
    queryKey: ["nerServices"],
    queryFn: listNERServices,
    staleTime: 5 * 60 * 1000,
  });

  const serviceOptions = useMemo(() => mapToServiceOptions(services), [services]);

  const canDetect =
    !!selectedServiceId?.trim() &&
    !!sourceLanguage?.trim() &&
    !!inputText?.trim() &&
    inputText.length <= MAX_TEXT_LENGTH &&
    !fetching;

  const handleProcess = async () => {
    const trimmedText = inputText.trim();
    if (!trimmedText) {
      const err = NER_ERRORS.TEXT_REQUIRED;
      showToast({ type: "error", message: err.description });
      return;
    }
    if (trimmedText.length < MIN_INFERENCE_TEXT_LENGTH) {
      const err = NER_ERRORS.TEXT_TOO_SHORT;
      showToast({ type: "error", message: err.description });
      return;
    }
    if (trimmedText.length > MAX_TEXT_LENGTH) {
      const err = NER_ERRORS.TEXT_TOO_LONG;
      showToast({ type: "error", message: err.description });
      return;
    }
    if (!selectedServiceId) {
      showToast({ type: "warning", message: "Please select a NER service." });
      return;
    }
    if (!sourceLanguage?.trim()) {
      showToast({ type: "warning", message: "Please select a language." });
      return;
    }

    setFetching(true);
    setError(null);
    setFetched(false);
    try {
      const startTime = Date.now();
      const response = await performNERInference(trimmedText, {
        serviceId: selectedServiceId,
        language: { sourceLanguage },
      });
      setResult(response.data);
      setResponseTime((Date.now() - startTime) / 1000);
      setFetched(true);
    } catch (err: unknown) {
      const { message: errorMessage } = parseError(err, { service: "ner" });
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

  const entities = result ? parseNerEntities(result) : [];

  return (
    <ServicePageLayout
      serviceId="ner"
      headDescription="Test Named Entity Recognition to identify entities in text"
      requestPanel={
        <RequestContainer
          serviceDropdown={{
            label: "NER Service",
            value: selectedServiceId,
            onChange: setSelectedServiceId,
            options: serviceOptions,
            loading: isLoadingServices,
            disabled: fetching,
            error: servicesError ? "Failed to load services. Please refresh the page." : null,
          }}
          languageConfig={{
            mode: "source-only",
            sourceLanguage,
            onSourceChange: setSourceLanguage,
            sourceOptions: INDIC_LANGUAGE_OPTIONS,
            disabled: fetching || !selectedServiceId,
          }}
          inputType="text"
          textInput={{
            value: inputText,
            onChange: setInputText,
            placeholder: pageDefaults.textPlaceholder,
            maxLength: MAX_TEXT_LENGTH,
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
          hasResult={!!result}
          metadata={
            fetched ? buildResponseMetadata({ responseTimeMs: responseTime * 1000 }) : []
          }
          result={
            fetched && result ? (
              <Box p={4} bg="gray.50" borderRadius="md" border="1px" borderColor="gray.200">
                <Text fontSize="sm" fontWeight="semibold" mb={3} color="gray.700">
                  Identified Entities:
                </Text>
                <VStack align="stretch" spacing={2}>
                  {entities.length === 0 ? (
                    <Text fontSize="sm" color="gray.500" fontStyle="italic">
                      No entities found in the text.
                    </Text>
                  ) : (
                    entities.map((entity, index) => (
                      <HStack key={index} spacing={2}>
                        <Badge colorScheme={getEntityColor(entity.label)} fontSize="xs" px={2} py={1} borderRadius="full">
                          {entity.label}
                        </Badge>
                        <Text fontSize="sm" color="gray.700">
                          {entity.text}
                        </Text>
                      </HStack>
                    ))
                  )}
                </VStack>
              </Box>
            ) : undefined
          }
          onClear={clearResults}
        />
      }
    />
  );
};

export default NERPage;
