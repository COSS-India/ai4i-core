// LLM service testing page — reusable service page architecture

import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FaLanguage } from "react-icons/fa";
import LLMResults from "../components/llm/LLMResults";
import {
  mapToServiceOptions,
  RequestContainer,
  ResponseContainer,
  ServicePageLayout,
} from "../components/service-page";
import { LLM_SUPPORTED_LANGUAGES } from "../config/constants";
import { getServicePageDefaults } from "../config/servicePageConfig";
import { useLLM } from "../hooks/useLLM";
import { listLLMServices } from "../services/llmService";
import {
  buildFeedbackContext,
  resolveServiceModelFallback,
} from "../utils/feedbackContext";

const pageDefaults = getServicePageDefaults("llm");
const languageOptions = LLM_SUPPORTED_LANGUAGES.map((l) => ({
  code: l.code,
  label: l.label,
}));

const LLMPage: React.FC = () => {
  const [serviceId, setServiceId] = useState<string>("");

  const {
    data: services = [],
    isLoading: isLoadingServices,
    isError: servicesError,
  } = useQuery({
    queryKey: ["llm-services"],
    queryFn: listLLMServices,
    staleTime: 5 * 60 * 1000,
  });

  const selectedService = useMemo(
    () => services.find((s) => s.service_id === serviceId),
    [services, serviceId]
  );
  const modelName = selectedService?.name ?? "";
  const selectedServiceId = selectedService?.service_id ?? "";

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
    lastRequestId,
    lastModelMeta,
    performInference,
    setInputText,
    setInputLanguage,
    setOutputLanguage,
    clearResults,
    swapLanguages,
  } = useLLM(selectedServiceId, modelName);

  const llmServiceOptions = useMemo(
    () => mapToServiceOptions(services),
    [services]
  );

  const feedback = useMemo(() => {
    if (!fetched || !outputText) return null;
    const fallback = resolveServiceModelFallback(selectedService);
    return buildFeedbackContext({
      requestId: lastRequestId,
      modelTaskType: "NMT",
      model: lastModelMeta,
      ...fallback,
      languageInfo: [
        {
          sourceLanguage: inputLanguage,
          targetLanguage: outputLanguage,
        },
      ],
      originalOutput: outputText,
    });
  }, [
    fetched,
    outputText,
    lastRequestId,
    lastModelMeta,
    selectedService,
    inputLanguage,
    outputLanguage,
  ]);

  const MAX_LLM_INPUT_LENGTH = pageDefaults.maxTextLength ?? 512;
  const canTranslate =
    !!serviceId?.trim() &&
    !!modelName?.trim() &&
    !!inputLanguage?.trim() &&
    !!outputLanguage?.trim() &&
    inputLanguage !== outputLanguage &&
    !!inputText?.trim() &&
    inputText.length <= MAX_LLM_INPUT_LENGTH;

  return (
    <ServicePageLayout
      serviceId="llm"
      headingSize="lg"
      headDescription="Test Large Language Model for text processing, translation, and generation"
      requestPanel={
        <RequestContainer
          serviceDropdown={{
            label: "LLM Service",
            value: serviceId,
            onChange: setServiceId,
            options: llmServiceOptions,
            loading: isLoadingServices,
            disabled: fetching,
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
            sourceOptions: languageOptions,
            targetOptions: languageOptions,
            onSwap: swapLanguages,
            disabled: fetching || !serviceId,
          }}
          inputType="text"
          textInput={{
            value: inputText,
            onChange: setInputText,
            maxLength: MAX_LLM_INPUT_LENGTH,
            disabled: fetching || !serviceId,
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
                onSwapTexts={swapLanguages}
              />
            ) : undefined
          }
          onClear={clearResults}
          feedback={feedback}
        />
      }
    />
  );
};

export default LLMPage;
