/**
 * Implicit feedback service.
 *
 * Sends fire-and-forget telemetry events to the feedback service when users
 * interact with NMT (or other inference) results.  Failures are silently
 * swallowed so they never affect the inference UI.
 *
 * Reward score semantics (±1.0 scale):
 *   +0.7  COPY_TRANSLATION  — user accepted and copied the output
 *   +0.1  COPY_SOURCE       — neutral informational copy
 *   -0.3  CLEAR_RESULTS     — user discarded the output
 *   -0.5  RETRANSLATE       — user immediately re-translated (not satisfied)
 *   -0.6  CORRECTION        — user edited source text after seeing the translation
 *   -1.0  ABANDON           — user navigated away without any positive interaction
 */

import apiClient, { apiEndpoints } from './api';
import { isAnonymousUser } from '../utils/anonymousSession';

export type ImplicitAction =
  | 'COPY_TRANSLATION'
  | 'COPY_SOURCE'
  | 'CLEAR_RESULTS'
  | 'RETRANSLATE'
  | 'CORRECTION'
  | 'ABANDON';

export const REWARD_SCORES: Record<ImplicitAction, number> = {
  COPY_TRANSLATION:  0.7,
  COPY_SOURCE:       0.1,
  CLEAR_RESULTS:    -0.3,
  RETRANSLATE:      -0.5,
  CORRECTION:       -0.6,
  ABANDON:          -1.0,
};

export interface ImplicitEventPayload {
  traceId: string;
  serviceId: string;
  taskType: 'nmt' | 'asr' | 'tts' | 'ocr';
  language: string;
  sourceInput: string;
  modelOutput: string;
  action: ImplicitAction;
}

/**
 * Send a single implicit feedback event.
 * Fire-and-forget: always resolves, never throws.
 * No-op for anonymous (unauthenticated) users.
 */
export const sendImplicitEvent = async (payload: ImplicitEventPayload): Promise<void> => {
  // Skip for anonymous users — they have no JWT and the endpoint requires one.
  if (isAnonymousUser()) return;

  try {
    await apiClient.post(apiEndpoints.feedback.event, {
      trace_id:     payload.traceId,
      service_id:   payload.serviceId,
      task_type:    payload.taskType,
      language:     payload.language,
      source_input: payload.sourceInput,
      model_output: payload.modelOutput,
      action:       payload.action,
      reward_score: REWARD_SCORES[payload.action],
    });
  } catch {
    // Never surface feedback errors to the user.
  }
};
