import { z } from "zod";

export const feedbackModelTaskTypeSchema = z.enum([
  "NMT",
  "ASR",
  "TTS",
  "OCR",
  "NER",
  "TRANSLITERATION",
  "TEXT_LANG_DETECTION",
  "AUDIO_LANG_DETECTION",
  "SPEAKER_DIARIZATION",
  "LANGUAGE_DIARIZATION",
]);

export const feedbackReasonSchema = z
  .object({
    code: z.string(),
    label: z.string(),
    description: z.string().optional(),
  })
  .passthrough();

export const feedbackReasonsResponseSchema = z
  .object({
    modelTaskType: feedbackModelTaskTypeSchema,
    reasons: z.array(feedbackReasonSchema),
  })
  .passthrough();

export const feedbackResponseSchema = z
  .object({
    status: z.string(),
    feedbackId: z.string(),
    message: z.string(),
  })
  .passthrough();
