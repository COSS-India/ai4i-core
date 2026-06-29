// LLM service testing page — reusable service page architecture

import React, { useEffect, useMemo, useState } from "react";
import { FaLanguage } from "react-icons/fa";
import LLMResults from "../components/llm/LLMResults";
import {
  mapToServiceOptions,
  RequestContainer,
  ResponseContainer,
  ServicePageLayout,
} from "../components/service-page";
import { LLM_SUPPORTED_LANGUAGES, MAX_LLM_TEXT_LENGTH } from '../constants';
import { getServicePageDefaults } from '../constants/servicePageConfig';
import { useLLM } from "../hooks/useLLM";
import { DEFAULT_LLM_SERVICES } from "../services/llmService";
import { LLM_CHAT_MODEL } from "../constants/modelManagement";

const pageDefaults = getServicePageDefaults("llm");
const languageOptions = LLM_SUPPORTED_LANGUAGES.map((l) => ({ code: l.code, label: l.label }));

const LLMPage: React.FC = () => {
  const [serviceId, setServiceId] = useState<string>(LLM_CHAT_MODEL);
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
    setSelectedModelId,
    clearResults,
    swapLanguages,
  } = useLLM(serviceId);

  const llmServiceOptions = useMemo(
    () => mapToServiceOptions(DEFAULT_LLM_SERVICES),
    []
  );

  useEffect(() => {
    setSelectedModelId(LLM_CHAT_MODEL);
  }, [setSelectedModelId]);

  const MAX_LLM_INPUT_LENGTH = pageDefaults.maxTextLength ?? MAX_LLM_TEXT_LENGTH;
  const canTranslate =
    !!serviceId?.trim() &&
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
            onChange: (id) => {
              setServiceId(id);
              setSelectedModelId(id);
            },
            options: llmServiceOptions,
            disabled: fetching,
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
        />
      }
    />
  );
};

export default LLMPage;
