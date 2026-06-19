// Transliteration testing page — reusable service page architecture

import { Box, Text } from "@chakra-ui/react";
import { useQuery } from "@tanstack/react-query";
import React, { useEffect, useMemo, useState } from "react";
import {
  buildResponseMetadata,
  INDIC_LANGUAGE_OPTIONS,
  mapToServiceOptions,
  RequestContainer,
  ResponseContainer,
  ServicePageLayout,
} from "../components/service-page";
import {
  TRANSLITERATION_ERRORS,
  MIN_TRANSLITERATION_TEXT_LENGTH,
  MAX_TEXT_LENGTH,
} from "../config/constants";
import { getServicePageDefaults } from "../config/servicePageConfig";
import { performTransliterationInference, listTransliterationServices } from "../services/transliterationService";
import { parseError } from "../utils/errorHandler";
import { useToastWithDeduplication } from "../utils/toast";

const pageDefaults = getServicePageDefaults("transliteration");

const TransliterationPage: React.FC = () => {
  const toast = useToastWithDeduplication();
  const [serviceId, setServiceId] = useState<string>("");
  const [inputText, setInputText] = useState("");
  const [sourceLanguage, setSourceLanguage] = useState("");
  const [targetLanguage, setTargetLanguage] = useState("");
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState(false);
  const [result, setResult] = useState<{ output?: Array<{ source?: string; target?: string }> } | null>(null);
  const [responseTime, setResponseTime] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  const targetLanguageOptions = useMemo(
    () => INDIC_LANGUAGE_OPTIONS.filter((lang) => lang.code !== sourceLanguage),
    [sourceLanguage]
  );

  useEffect(() => {
    if (targetLanguage && targetLanguage === sourceLanguage) {
      setTargetLanguage("");
    }
  }, [sourceLanguage, targetLanguage]);

  const { data: transliterationServices, isLoading: servicesLoading } = useQuery({
    queryKey: ["transliteration-services"],
    queryFn: listTransliterationServices,
    staleTime: 10 * 60 * 1000,
  });

  const serviceOptions = useMemo(
    () => mapToServiceOptions(transliterationServices ?? []),
    [transliterationServices]
  );

  const canTransliterate =
    !!serviceId?.trim() &&
    !!sourceLanguage?.trim() &&
    !!targetLanguage?.trim() &&
    !!inputText?.trim() &&
    inputText.length <= MAX_TEXT_LENGTH &&
    !fetching;

  const handleProcess = async () => {
    const trimmedText = inputText.trim();
    if (!serviceId?.trim()) {
      toast({ title: "Service Required", description: "Please select a transliteration.", status: "warning", duration: 3000, isClosable: true });
      return;
    }
    if (!sourceLanguage?.trim() || !targetLanguage?.trim()) {
      toast({ title: "Language Required", description: "Please select both source and target languages.", status: "warning", duration: 3000, isClosable: true });
      return;
    }
    if (!trimmedText) {
      const err = TRANSLITERATION_ERRORS.TEXT_REQUIRED;
      toast({ title: err.title, description: err.description, status: "error", duration: 3000, isClosable: true });
      return;
    }
    if (trimmedText.length < MIN_TRANSLITERATION_TEXT_LENGTH) {
      const err = TRANSLITERATION_ERRORS.TEXT_TOO_SHORT;
      toast({ title: err.title, description: err.description, status: "error", duration: 3000, isClosable: true });
      return;
    }
    if (trimmedText.length > MAX_TEXT_LENGTH) {
      const err = TRANSLITERATION_ERRORS.TEXT_TOO_LONG;
      toast({ title: err.title, description: err.description, status: "error", duration: 3000, isClosable: true });
      return;
    }

    setFetching(true);
    setError(null);
    setFetched(false);
    try {
      const startTime = Date.now();
      const response = await performTransliterationInference(trimmedText, {
        serviceId,
        language: { sourceLanguage, targetLanguage },
        isSentence: true,
        numSuggestions: 0,
      });
      setResult(response.data);
      setResponseTime((Date.now() - startTime) / 1000);
      setFetched(true);
    } catch (err: unknown) {
      const { message: errorMessage } = parseError(err, { service: "transliteration" });
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

  const hasOutput = !!(result?.output && result.output.length > 0);

  return (
    <ServicePageLayout
      serviceId="transliteration"
      headDescription="Test Transliteration to convert text between scripts"
      requestPanel={
        <RequestContainer
          serviceDropdown={{
            label: "Transliteration",
            value: serviceId,
            onChange: setServiceId,
            options: serviceOptions,
            loading: servicesLoading,
            disabled: fetching,
          }}
          languageConfig={{
            mode: "source-target",
            sourceLanguage,
            targetLanguage,
            onSourceChange: setSourceLanguage,
            onTargetChange: setTargetLanguage,
            sourceOptions: INDIC_LANGUAGE_OPTIONS,
            targetOptions: targetLanguageOptions,
            disabled: fetching || !serviceId,
          }}
          inputType="text"
          textInput={{
            value: inputText,
            onChange: setInputText,
            placeholder: pageDefaults.textPlaceholder,
            maxLength: MAX_TEXT_LENGTH,
            disabled: fetching || !serviceId,
          }}
          helperText={pageDefaults.helperText}
          submitButton={{
            label: pageDefaults.submitLabel,
            loadingLabel: pageDefaults.submitLoadingLabel,
            onClick: handleProcess,
            isLoading: fetching,
            isDisabled: !canTransliterate,
          }}
        />
      }
      responsePanel={
        <ResponseContainer
          fetching={fetching}
          fetchingLabel="Processing text..."
          error={error}
          fetched={fetched}
          hasResult={hasOutput}
          metadata={
            fetched ? buildResponseMetadata({ responseTimeMs: responseTime * 1000 }) : []
          }
          result={
            hasOutput ? (
              <Box p={4} bg="blue.50" borderRadius="md" border="1px" borderColor="blue.200">
                <Text fontSize="sm" fontWeight="semibold" mb={2} color="gray.700">
                  Transliterated Text:
                </Text>
                {result!.output!.map((item, index) => (
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
            ) : undefined
          }
          onClear={clearResults}
        />
      }
    />
  );
};

export default TransliterationPage;
