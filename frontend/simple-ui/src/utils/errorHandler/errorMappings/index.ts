import {
  ASR_ERRORS,
  AUDIO_LANGUAGE_DETECTION_ERRORS,
  COMMON_ERRORS,
  LANGUAGE_DETECTION_ERRORS,
  NER_ERRORS,
  NMT_ERRORS,
  OCR_ERRORS,
  PIPELINE_ERRORS,
  SPEAKER_DIARIZATION_ERRORS,
  TRANSLITERATION_ERRORS,
  TTS_ERRORS,
} from "../../../config/constants";
import type { ErrorCatalog, ErrorDetail, ErrorHandlerService, ErrorInfo } from "../types";
import { formatErrorCode } from "../formatErrorCode";

export const SERVICE_ERROR_CATALOGS: Record<ErrorHandlerService, ErrorCatalog> = {
  asr: ASR_ERRORS,
  tts: TTS_ERRORS,
  nmt: NMT_ERRORS,
  pipeline: PIPELINE_ERRORS,
  ocr: OCR_ERRORS,
  transliteration: TRANSLITERATION_ERRORS,
  "language-detection": LANGUAGE_DETECTION_ERRORS,
  "speaker-diarization": SPEAKER_DIARIZATION_ERRORS,
  "audio-language-detection": AUDIO_LANGUAGE_DETECTION_ERRORS,
  ner: NER_ERRORS,
};

function applyRateLimitMessage(errorCode: string, detail: ErrorDetail, message: string): string {
  if (errorCode === "RATE_LIMIT_EXCEEDED" && detail.retryAfter) {
    return `Too many requests. Please wait ${detail.retryAfter} seconds before trying again.`;
  }
  return message;
}

function applyLanguagePairMessage(
  service: ErrorHandlerService | undefined,
  errorCode: string,
  detail: ErrorDetail,
  description: string
): string {
  if (
    service === "nmt" &&
    errorCode === "LANGUAGE_PAIR_NOT_SUPPORTED"
  ) {
    const source = String(detail.sourceLanguage ?? detail.source ?? "source");
    const target = String(detail.targetLanguage ?? detail.target ?? "target");
    return description.replace("{source}", source).replace("{target}", target);
  }

  if (
    service === "pipeline" &&
    errorCode === "S2S_LANGUAGE_PAIR_NOT_SUPPORTED"
  ) {
    const source = String(detail.sourceLanguage ?? detail.source ?? "source");
    const target = String(detail.targetLanguage ?? detail.target ?? "target");
    return description.replace("{source}", source).replace("{target}", target);
  }

  return description;
}

function buildMappedError(
  errorCode: string,
  entry: { title: string; description: string },
  detail: ErrorDetail,
  service?: ErrorHandlerService
): ErrorInfo {
  const baseDescription = applyLanguagePairMessage(
    service,
    errorCode,
    detail,
    entry.description
  );
  const message = applyRateLimitMessage(
    errorCode,
    detail,
    String(detail.message ?? baseDescription)
  );

  return {
    title: entry.title,
    message,
    showOnlyMessage: true,
  };
}

/**
 * Resolve a structured API error code against common + service catalogs.
 * ASR catalog is always checked as a fallback (legacy behavior).
 */
export function resolveMappedServiceError(
  service: ErrorHandlerService | undefined,
  errorCode: string,
  detail: ErrorDetail
): ErrorInfo | null {
  if (COMMON_ERRORS[errorCode as keyof typeof COMMON_ERRORS]) {
    const commonError = COMMON_ERRORS[errorCode as keyof typeof COMMON_ERRORS];
    return buildMappedError(errorCode, commonError, detail, service);
  }

  if (service && SERVICE_ERROR_CATALOGS[service]?.[errorCode]) {
    return buildMappedError(
      errorCode,
      SERVICE_ERROR_CATALOGS[service][errorCode],
      detail,
      service
    );
  }

  if (ASR_ERRORS[errorCode as keyof typeof ASR_ERRORS]) {
    return buildMappedError(
      errorCode,
      ASR_ERRORS[errorCode as keyof typeof ASR_ERRORS],
      detail,
      service
    );
  }

  return null;
}

export function resolveUnknownCodeError(
  errorCode: string,
  detail: ErrorDetail,
  fallbackMessage: string
): ErrorInfo {
  if (errorCode === "PERMISSION_DENIED" || errorCode.includes("PERMISSION_DENIED")) {
    return {
      title: "PERMISSION DENIED",
      message: detail.message
        ? String(detail.message)
        : "You do not have the required permissions to perform this action.",
      showOnlyMessage: true,
    };
  }

  return {
    title: formatErrorCode(errorCode),
    message: fallbackMessage,
    showOnlyMessage: true,
  };
}
