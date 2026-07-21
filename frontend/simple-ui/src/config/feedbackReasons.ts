/**
 * Default Explicit Feedback reasons per model task type.
 * Used when GET /feedback/reasons is unavailable; mirrors PRD defaults.
 * Codes are stable snake_case identifiers submitted in POST /feedback.
 */

import type { FeedbackModelTaskType, FeedbackReason } from "../types/feedback";

export const DEFAULT_FEEDBACK_REASONS: Record<
  FeedbackModelTaskType,
  FeedbackReason[]
> = {
  NMT: [
    {
      code: "incorrect_meaning",
      label: "Incorrect meaning",
      description:
        "The translated output changes, loses, or misrepresents the meaning of the original content.",
    },
    {
      code: "unnatural_phrasing",
      label: "Unnatural phrasing",
      description:
        "The translation contains grammatical mistakes or does not read naturally in the target language.",
    },
    {
      code: "missing_translation",
      label: "Missing translation",
      description:
        "Part of the original content was not translated and is absent in the output.",
    },
    {
      code: "wrong_terminology",
      label: "Wrong terminology",
      description:
        "A domain-specific term such as a medical, legal, or technical word was translated incorrectly.",
    },
    {
      code: "other",
      label: "Other",
      description: "The issue does not fit any of the above categories.",
    },
  ],
  ASR: [
    {
      code: "missing_words",
      label: "Missing words",
      description: "Words spoken in the audio are absent in the transcribed output.",
    },
    {
      code: "additional_words",
      label: "Additional words",
      description:
        "Words appear in the transcript that were never spoken in the audio.",
    },
    {
      code: "incomplete_transcription",
      label: "Incomplete transcription",
      description: "Only part of the audio was transcribed.",
    },
    {
      code: "wrong_language_detected",
      label: "Wrong language detected",
      description:
        "The spoken language was identified incorrectly, resulting in an inaccurate transcription.",
    },
    {
      code: "other",
      label: "Other",
      description: "The issue does not fit any of the above categories.",
    },
  ],
  TTS: [
    {
      code: "unnatural_speech",
      label: "Unnatural speech",
      description: "Speech sounds robotic, unnatural, or lacks fluency.",
    },
    {
      code: "wrong_accent",
      label: "Wrong accent",
      description: "Speech is generated with an inappropriate accent or dialect.",
    },
    {
      code: "missing_speech_content",
      label: "Missing speech content",
      description:
        "Portions of the input text are not spoken in the generated audio.",
    },
    {
      code: "poor_audio_quality",
      label: "Poor audio quality",
      description:
        "Audio contains distortion, clipping, noise, or quality degradation.",
    },
    {
      code: "other",
      label: "Other",
      description: "The issue does not fit any of the above categories.",
    },
  ],
  OCR: [
    {
      code: "missing_text",
      label: "Missing text",
      description: "Portions of the document were not extracted.",
    },
    {
      code: "layout_recognition_error",
      label: "Layout recognition error",
      description:
        "Document structure, paragraphs, or sections were interpreted incorrectly.",
    },
    {
      code: "table_recognition_error",
      label: "Table recognition error",
      description: "Table content or structure was extracted incorrectly.",
    },
    {
      code: "partial_extraction",
      label: "Partial extraction",
      description: "Only a portion of the document was processed or extracted.",
    },
    {
      code: "other",
      label: "Other",
      description: "The issue does not fit any of the above categories.",
    },
  ],
  NER: [
    {
      code: "missing_entity",
      label: "Missing entity",
      description: "An expected entity was not identified.",
    },
    {
      code: "incorrect_entity",
      label: "Incorrect entity",
      description: "An extracted entity is incorrect.",
    },
    {
      code: "wrong_entity_type",
      label: "Wrong entity type",
      description: "The entity was classified under the wrong category.",
    },
    {
      code: "incorrect_entity_boundary",
      label: "Incorrect entity boundary",
      description: "The entity span includes too much or too little text.",
    },
    {
      code: "duplicate_entity",
      label: "Duplicate entity",
      description: "The same entity was identified multiple times unnecessarily.",
    },
    {
      code: "other",
      label: "Other",
      description: "The issue does not fit any of the above categories.",
    },
  ],
  TRANSLITERATION: [
    {
      code: "pronunciation_mismatch",
      label: "Pronunciation mismatch",
      description:
        "The transliterated output does not reflect the intended pronunciation.",
    },
    {
      code: "missing_characters",
      label: "Missing characters",
      description: "Characters from the original text are omitted.",
    },
    {
      code: "additional_characters",
      label: "Additional characters",
      description: "Extra characters are introduced in the output.",
    },
    {
      code: "other",
      label: "Other",
      description: "The issue does not fit any of the above categories.",
    },
  ],
  TEXT_LANG_DETECTION: [
    {
      code: "language_not_detected",
      label: "Language not detected",
      description: "The system failed to identify the language.",
    },
    {
      code: "code_mixed_language_not_identified",
      label: "Code-mixed language not identified",
      description: "Mixed-language text was not recognized correctly.",
    },
    {
      code: "multiple_languages_present",
      label: "Multiple languages present",
      description:
        "Text containing multiple languages was classified incorrectly.",
    },
    {
      code: "other",
      label: "Other",
      description: "The issue does not fit any of the above categories.",
    },
  ],
  AUDIO_LANG_DETECTION: [
    {
      code: "language_not_detected",
      label: "Language not detected",
      description: "The system failed to identify the spoken language.",
    },
    {
      code: "code_mixed_language_not_identified",
      label: "Code-mixed language not identified",
      description: "Mixed-language speech was not recognized correctly.",
    },
    {
      code: "multiple_languages_misclassified",
      label: "Multiple languages misclassified",
      description:
        "Audio containing multiple languages was classified incorrectly.",
    },
    {
      code: "other",
      label: "Other",
      description: "The issue does not fit any of the above categories.",
    },
  ],
  SPEAKER_DIARIZATION: [
    {
      code: "incorrect_speaker_segmentation",
      label: "Incorrect speaker segmentation",
      description: "Speaker change points were detected incorrectly.",
    },
    {
      code: "speaker_merge_error",
      label: "Speaker merge error",
      description: "Multiple speakers were incorrectly grouped as one speaker.",
    },
    {
      code: "speaker_split_error",
      label: "Speaker split error",
      description:
        "A single speaker was incorrectly identified as multiple speakers.",
    },
    {
      code: "missing_speaker",
      label: "Missing speaker",
      description: "One or more speakers were not identified.",
    },
    {
      code: "timestamp_error",
      label: "Timestamp error",
      description: "Speaker timestamps or boundaries are inaccurate.",
    },
    {
      code: "other",
      label: "Other",
      description: "The issue does not fit any of the above categories.",
    },
  ],
  LANGUAGE_DIARIZATION: [
    {
      code: "incorrect_language_segmentation",
      label: "Incorrect language segmentation",
      description: "Language change points were detected incorrectly.",
    },
    {
      code: "missing_language_segment",
      label: "Missing language segment",
      description: "One or more language segments were not identified.",
    },
    {
      code: "wrong_language_identification",
      label: "Wrong language identification",
      description: "A language segment was assigned the wrong language.",
    },
    {
      code: "timestamp_error",
      label: "Timestamp error",
      description: "Language boundaries or timestamps are inaccurate.",
    },
    {
      code: "other",
      label: "Other",
      description: "The issue does not fit any of the above categories.",
    },
  ],
};

/** Task types that support editing a preloaded text correction. */
export const CORRECTED_OUTPUT_TASK_TYPES: ReadonlySet<FeedbackModelTaskType> =
  new Set<FeedbackModelTaskType>([
    "NMT",
    "ASR",
    "OCR",
    "NER",
    "TRANSLITERATION",
    "TEXT_LANG_DETECTION",
  ]);

export const DEFAULT_FEEDBACK_LABELS = {
  prompt: "How was this?",
  detailTitle: "What went wrong?",
  commentPlaceholder: "Add more details (optional)",
  correctedOutputLabel: "Suggested correction",
  correctedOutputPlaceholder: "Edit the response to what it should have been",
  submit: "Submit feedback",
  skip: "Skip",
  thanksPositive: "Thanks for your feedback!",
  thanksNegative: "Thanks — your feedback helps improve the model.",
  reasonsLoading: "Loading reasons…",
  reasonsError: "Could not load reasons. Using defaults.",
  rateHelpful: "Rate as helpful",
  rateNotHelpful: "Rate as not helpful",
} as const;

/** Map portal/service page ids to Feedback API modelTaskType values. */
export const SERVICE_ID_TO_FEEDBACK_TASK: Record<string, FeedbackModelTaskType> =
  {
    nmt: "NMT",
    asr: "ASR",
    tts: "TTS",
    ocr: "OCR",
    ner: "NER",
    transliteration: "TRANSLITERATION",
    "language-detection": "TEXT_LANG_DETECTION",
    "audio-language-detection": "AUDIO_LANG_DETECTION",
    "speaker-diarization": "SPEAKER_DIARIZATION",
    "language-diarization": "LANGUAGE_DIARIZATION",
    /** Portal LLM chat is translation-oriented; Feedback API has no LLM type yet. */
    llm: "NMT",
    /** Speech-to-Speech: rate the NMT (translation) stage of the pipeline. */
    pipeline: "NMT",
  };

export function getDefaultReasons(
  modelTaskType: FeedbackModelTaskType,
): FeedbackReason[] {
  return DEFAULT_FEEDBACK_REASONS[modelTaskType] ?? [];
}

export function supportsCorrectedOutput(
  modelTaskType: FeedbackModelTaskType,
): boolean {
  return CORRECTED_OUTPUT_TASK_TYPES.has(modelTaskType);
}
