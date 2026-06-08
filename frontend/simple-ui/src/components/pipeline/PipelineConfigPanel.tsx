// Language and service configuration for the speech-to-speech pipeline page

import React, { useEffect, useMemo } from "react";
import { VStack } from "@chakra-ui/react";
import {
  LanguageConfig,
  mapToServiceOptions,
  ServiceDropdown,
} from "../service-page";
import { ASR_SUPPORTED_LANGUAGES, TTS_SUPPORTED_LANGUAGES } from "../../config/constants";
import type { ASRServiceDetails } from "../../services/asrService";
import type { TTSServiceDetailsResponse } from "../../services/ttsService";
import type { ServiceListItem } from "../service-page/utils";

const asrLanguageOptions = ASR_SUPPORTED_LANGUAGES.map((l) => ({
  code: l.code,
  label: l.label,
}));

export interface PipelineConfigPanelProps {
  sourceLanguage: string;
  targetLanguage: string;
  asrServiceId: string;
  nmtServiceId: string;
  ttsServiceId: string;
  asrServices?: ASRServiceDetails[];
  nmtServices?: ServiceListItem[];
  ttsServices?: TTSServiceDetailsResponse[];
  disabled?: boolean;
  onSourceLanguageChange: (code: string) => void;
  onTargetLanguageChange: (code: string) => void;
  onAsrServiceChange: (id: string) => void;
  onNmtServiceChange: (id: string) => void;
  onTtsServiceChange: (id: string) => void;
}

const PipelineConfigPanel: React.FC<PipelineConfigPanelProps> = ({
  sourceLanguage,
  targetLanguage,
  asrServiceId,
  nmtServiceId,
  ttsServiceId,
  asrServices,
  nmtServices,
  ttsServices,
  disabled = false,
  onSourceLanguageChange,
  onTargetLanguageChange,
  onAsrServiceChange,
  onNmtServiceChange,
  onTtsServiceChange,
}) => {
  const targetLanguageOptions = useMemo(
    () =>
      TTS_SUPPORTED_LANGUAGES.filter((lang) => lang.code !== sourceLanguage).map((l) => ({
        code: l.code,
        label: l.label,
      })),
    [sourceLanguage]
  );

  useEffect(() => {
    if (targetLanguage && targetLanguage === sourceLanguage) {
      onTargetLanguageChange("");
    }
  }, [sourceLanguage, targetLanguage, onTargetLanguageChange]);

  const asrOptions = useMemo(() => mapToServiceOptions(asrServices ?? []), [asrServices]);

  const nmtOptions = useMemo(
    () =>
      mapToServiceOptions(
        (nmtServices ?? []).filter(
          (service) => !service.service_id.toLowerCase().includes("facebook")
        )
      ),
    [nmtServices]
  );

  const ttsOptions = useMemo(() => mapToServiceOptions(ttsServices ?? []), [ttsServices]);

  return (
    <VStack spacing={6} align="stretch">
      <LanguageConfig
        mode="source-target"
        sourceLanguage={sourceLanguage}
        targetLanguage={targetLanguage}
        onSourceChange={onSourceLanguageChange}
        onTargetChange={onTargetLanguageChange}
        sourceOptions={asrLanguageOptions}
        targetOptions={targetLanguageOptions}
        disabled={disabled}
      />
      <ServiceDropdown
        label="ASR Service"
        value={asrServiceId}
        onChange={onAsrServiceChange}
        options={asrOptions}
        disabled={disabled}
      />
      <ServiceDropdown
        label="NMT Service"
        value={nmtServiceId}
        onChange={onNmtServiceChange}
        options={nmtOptions}
        disabled={disabled}
      />
      <ServiceDropdown
        label="TTS Service"
        value={ttsServiceId}
        onChange={onTtsServiceChange}
        options={ttsOptions}
        disabled={disabled}
      />
    </VStack>
  );
};

export default PipelineConfigPanel;
