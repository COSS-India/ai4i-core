// Reusable AI service page architecture — public API

export { default as ServicePageLayout } from "./ServicePageLayout";
export { default as GuestUsageLimitBanner } from "./GuestUsageLimitBanner";
export { default as RequestContainer } from "./RequestContainer";
export { default as ResponseContainer } from "./ResponseContainer";
export { default as ServiceDropdown } from "./ServiceDropdown";
export { default as LanguageConfig } from "./LanguageConfig";
export { default as HelperText } from "./HelperText";
export { default as SubmitButton } from "./SubmitButton";
export { default as TextInput } from "./inputs/TextInput";
export { default as AudioInput } from "./inputs/AudioInput";
export { default as ImageInput } from "./inputs/ImageInput";
export { default as ResultDisplay } from "./response/ResultDisplay";
export { default as ResponseMetadata } from "./response/ResponseMetadata";
export { default as ResponseActions } from "./response/ResponseActions";
export { mapToServiceOptions } from "./utils";
export { INDIC_LANGUAGE_OPTIONS } from "../../constants/languages";
export type { ServiceListItem } from "./utils";

export type {
  ServiceInputType,
  LanguageConfigMode,
  ServiceOption,
  LanguageOption,
  LanguagePairOption,
  ResponseMetadataItem,
  ResponseActionConfig,
  ResponseActionKind,
  ServiceDropdownProps,
  LanguageConfigProps,
  ServiceTextInputProps,
  ServiceAudioInputProps,
  ServiceImageInputProps,
  SubmitButtonProps,
  RequestContainerProps,
  ResponseContainerProps,
  ServicePageLayoutProps,
} from "../../types/servicePage";

export { useCopyToClipboard, downloadTextFile } from "../../hooks/useCopyToClipboard";

import type { ResponseMetadataItem } from "../../types/servicePage";

/** Build standard response metadata from common inference stats */
export function buildResponseMetadata(options: {
  requestWordCount?: number;
  responseWordCount?: number;
  responseTimeMs?: number;
  confidence?: number;
  tokenCount?: number;
}): ResponseMetadataItem[] {
  const items: ResponseMetadataItem[] = [];

  if (options.requestWordCount !== undefined) {
    items.push({ label: "Request word count", value: options.requestWordCount });
  }
  if (options.responseWordCount !== undefined) {
    items.push({ label: "Response word count", value: options.responseWordCount });
  }
  if (options.tokenCount !== undefined) {
    items.push({ label: "Token count", value: options.tokenCount });
  }
  if (options.responseTimeMs !== undefined) {
    items.push({
      label: "Response time",
      value: `${(options.responseTimeMs / 1000).toFixed(2)}s`,
    });
  }
  if (options.confidence !== undefined) {
    items.push({
      label: "Confidence",
      value: `${(options.confidence * 100).toFixed(1)}%`,
      helpText: "Accuracy",
    });
  }

  return items;
}
