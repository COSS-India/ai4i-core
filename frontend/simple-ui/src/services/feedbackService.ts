/**
 * Explicit Feedback API client — POST /feedback and GET /feedback/reasons.
 */

import { getDefaultReasons } from "../config/feedbackReasons";
import type {
  FeedbackModelTaskType,
  FeedbackReason,
  FeedbackReasonsResponse,
  FeedbackResponse,
  FeedbackSubmission,
} from "../types/feedback";
import { apiService, apiEndpoints } from "./api";
import {
  feedbackReasonsResponseSchema,
  feedbackResponseSchema,
} from "./dto/schemas/feedback";

export async function submitFeedback(
  payload: FeedbackSubmission,
): Promise<FeedbackResponse> {
  const response = await apiService.post<FeedbackResponse>(
    apiEndpoints.feedback.submit,
    payload,
    {
      responseSchema: feedbackResponseSchema,
      suppressErrorAlert: true,
    },
  );
  return response.data;
}

/**
 * Load task-specific feedback reasons from the catalog API.
 * Falls back to PRD defaults when the endpoint is unavailable (404/network).
 */
export async function fetchFeedbackReasons(
  modelTaskType: FeedbackModelTaskType,
): Promise<{ reasons: FeedbackReason[]; fromFallback: boolean }> {
  try {
    const response = await apiService.get<FeedbackReasonsResponse>(
      apiEndpoints.feedback.reasons(modelTaskType),
      {
        responseSchema: feedbackReasonsResponseSchema,
        suppressErrorAlert: true,
      },
    );
    const reasons = response.data?.reasons ?? [];
    if (reasons.length === 0) {
      return { reasons: getDefaultReasons(modelTaskType), fromFallback: true };
    }
    return { reasons, fromFallback: false };
  } catch {
    return { reasons: getDefaultReasons(modelTaskType), fromFallback: true };
  }
}
