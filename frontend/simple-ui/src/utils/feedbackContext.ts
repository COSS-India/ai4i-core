/**
 * Helpers for attaching Explicit Feedback context to inference responses.
 */

import type { AxiosResponse } from "axios";
import type {
  FeedbackContext,
  FeedbackLanguageInfo,
  FeedbackModelTaskType,
  InferenceModelMetadata,
} from "../types/feedback";

function headerValue(
  headers: AxiosResponse["headers"],
  name: string,
): string | undefined {
  if (!headers) return undefined;
  const lower = name.toLowerCase();
  const raw =
    (headers as Record<string, unknown>)[name] ??
    (headers as Record<string, unknown>)[lower] ??
    (typeof (headers as { get?: (k: string) => unknown }).get === "function"
      ? (headers as { get: (k: string) => unknown }).get(name) ||
        (headers as { get: (k: string) => unknown }).get(lower)
      : undefined);
  if (raw == null) return undefined;
  const value = String(raw).trim();
  return value || undefined;
}

/** Read X-Correlation-ID from an inference axios response (Feedback requestId). */
export function getCorrelationIdFromHeaders(
  headers: AxiosResponse["headers"],
): string | undefined {
  return (
    headerValue(headers, "x-correlation-id") ||
    headerValue(headers, "X-Correlation-ID")
  );
}

export function normalizeModelMetadata(
  model: InferenceModelMetadata | null | undefined,
): {
  modelProvider?: string;
  modelVersion?: string;
  modelId?: string;
  languageInfo?: FeedbackLanguageInfo[];
} {
  if (!model) return {};
  const languageInfo = Array.isArray(model.language)
    ? model.language.map((entry) => ({
        sourceLanguage: entry?.sourceLanguage,
        targetLanguage: entry?.targetLanguage,
      }))
    : undefined;

  return {
    modelProvider: model.modelProvider?.trim() || undefined,
    modelVersion: model.modelVersion?.trim() || undefined,
    modelId: model.modelId?.trim() || undefined,
    languageInfo,
  };
}

export interface BuildFeedbackContextInput {
  requestId?: string | null;
  modelTaskType: FeedbackModelTaskType;
  model?: InferenceModelMetadata | null;
  /** Fallback when inference `model` block is missing. */
  modelProvider?: string;
  modelVersion?: string;
  modelId?: string;
  languageInfo?: FeedbackLanguageInfo[];
  originalOutput?: string;
}

/**
 * Build FeedbackWidget context. Returns null when required attribution
 * fields (requestId, provider, version) are missing.
 */
export function buildFeedbackContext(
  input: BuildFeedbackContextInput,
): FeedbackContext | null {
  const fromModel = normalizeModelMetadata(input.model);
  const requestId = input.requestId?.trim();
  const modelProvider =
    fromModel.modelProvider || input.modelProvider?.trim() || "";
  const modelVersion =
    fromModel.modelVersion || input.modelVersion?.trim() || "";

  if (!requestId || !modelProvider || !modelVersion) {
    return null;
  }

  return {
    requestId,
    modelTaskType: input.modelTaskType,
    modelProvider,
    modelVersion,
    modelId: fromModel.modelId || input.modelId,
    languageInfo: fromModel.languageInfo || input.languageInfo,
    originalOutput: input.originalOutput,
  };
}

export function extractInferenceFeedbackMeta(response: AxiosResponse): {
  requestId?: string;
  responseTime: number;
  model?: InferenceModelMetadata;
} {
  const requestId = getCorrelationIdFromHeaders(response.headers);
  const responseTime = Number.parseInt(
    headerValue(response.headers, "request-duration") || "0",
    10,
  );
  const model = (response.data as { model?: InferenceModelMetadata } | undefined)
    ?.model;
  return { requestId, responseTime, model };
}

/** Resolve provider/version/id from a selected service list item (fallback). */
export function resolveServiceModelFallback(service?: {
  provider?: string;
  name?: string;
  service_id?: string;
  model_id?: string;
  model_version?: string;
  modelVersion?: string;
} | null): {
  modelProvider?: string;
  modelVersion?: string;
  modelId?: string;
} {
  if (!service) return {};
  return {
    modelProvider:
      service.provider?.trim() ||
      service.name?.trim() ||
      service.service_id?.trim() ||
      undefined,
    modelVersion:
      service.modelVersion?.trim() || service.model_version?.trim() || undefined,
    modelId: service.model_id?.trim() || undefined,
  };
}
