/**
 * Explicit Feedback Framework types (v0.1 — thumbs up/down).
 * Aligned with POST /api/v1/feedback and GET /api/v1/feedback/reasons.
 */

export type FeedbackRating = "POSITIVE" | "NEGATIVE";

export type FeedbackType = "THUMBS";

/** Public Feedback API model task vocabulary (SCREAMING_SNAKE_CASE). */
export type FeedbackModelTaskType =
  | "NMT"
  | "ASR"
  | "TTS"
  | "OCR"
  | "NER"
  | "TRANSLITERATION"
  | "TEXT_LANG_DETECTION"
  | "AUDIO_LANG_DETECTION"
  | "SPEAKER_DIARIZATION"
  | "LANGUAGE_DIARIZATION";

export interface FeedbackLanguageInfo {
  sourceLanguage?: string;
  targetLanguage?: string;
}

export interface FeedbackReason {
  code: string;
  label: string;
  description?: string;
}

export interface FeedbackSubmission {
  requestId: string;
  modelTaskType: FeedbackModelTaskType;
  feedbackType: FeedbackType;
  rating: FeedbackRating;
  reasons?: string[];
  comments?: string;
  correctedOutput?: string;
  modelProvider: string;
  modelVersion: string;
  modelId?: string;
  tenantId?: string;
  languageInfo?: FeedbackLanguageInfo[];
}

export interface FeedbackResponse {
  status: string;
  feedbackId: string;
  message: string;
}

export interface FeedbackReasonsResponse {
  modelTaskType: FeedbackModelTaskType;
  reasons: FeedbackReason[];
}

/** Model identity echoed from the enriched inference response. */
export interface InferenceModelMetadata {
  modelProvider?: string | null;
  modelVersion?: string | null;
  modelId?: string | null;
  language?: FeedbackLanguageInfo[];
}

/** Context required to attribute feedback to a specific inference call. */
export interface FeedbackContext {
  requestId: string;
  modelTaskType: FeedbackModelTaskType;
  modelProvider: string;
  modelVersion: string;
  modelId?: string;
  languageInfo?: FeedbackLanguageInfo[];
  /** Preloaded model output for corrected-output editing (NMT/ASR/etc.). */
  originalOutput?: string;
}

export interface FeedbackWidgetLabels {
  prompt: string;
  detailTitle: string;
  commentPlaceholder: string;
  correctedOutputLabel: string;
  correctedOutputPlaceholder: string;
  submit: string;
  skip: string;
  thanksPositive: string;
  thanksNegative: string;
  reasonsLoading: string;
  reasonsError: string;
  rateHelpful: string;
  rateNotHelpful: string;
}

export type FeedbackWidgetAccent = {
  /** Chakra color scheme name (e.g. "orange", "blue") or CSS color for accents */
  colorScheme?: string;
  /** Optional CSS color override for accent (buttons, focus). */
  accentColor?: string;
  /** Panel background for thumbs-down detail (default warm cream). */
  detailPanelBg?: string;
};
