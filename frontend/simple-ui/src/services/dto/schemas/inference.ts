import { z } from 'zod';

/**
 * Loose inference response validation — only enforces top-level array shape.
 * Detailed fields are typed in `src/types/inference.ts` without runtime strictness.
 */

const looseRecord = z.record(z.unknown());

/** `output` array present (most inference tasks). */
export const inferenceOutputResponseSchema = z
  .object({
    output: z.array(looseRecord),
  })
  .passthrough();

/** TTS returns `audio` instead of `output`. */
export const inferenceAudioResponseSchema = z
  .object({
    audio: z.array(looseRecord),
  })
  .passthrough();

// Per-service exports (same loose shape; kept for stable import paths)
export const asrInferenceResponseSchema = inferenceOutputResponseSchema;
export const nmtInferenceResponseSchema = inferenceOutputResponseSchema;
export const llmInferenceResponseSchema = inferenceOutputResponseSchema;

/** OpenAI-style chat completion from POST /api/v1/chat/completions */
export const chatCompletionResponseSchema = z
  .object({
    choices: z.array(
      z
        .object({
          message: z
            .object({
              content: z.string(),
            })
            .passthrough(),
        })
        .passthrough()
    ),
  })
  .passthrough();
export const ocrInferenceResponseSchema = inferenceOutputResponseSchema;
export const nerInferenceResponseSchema = inferenceOutputResponseSchema;
export const languageDetectionInferenceResponseSchema = inferenceOutputResponseSchema;
export const transliterationInferenceResponseSchema = inferenceOutputResponseSchema;
export const speakerDiarizationInferenceResponseSchema = inferenceOutputResponseSchema;
export const languageDiarizationInferenceResponseSchema = inferenceOutputResponseSchema;
export const audioLanguageDetectionInferenceResponseSchema = inferenceOutputResponseSchema;
export const ttsInferenceResponseSchema = inferenceAudioResponseSchema;

const healthComponentsSchema = z.record(
  z.string(),
  z
    .object({
      status: z.string(),
      details: z.unknown().optional(),
    })
    .passthrough()
);

export const asrModelsResponseSchema = z.object({
  models: z.array(
    z
      .object({
        model_id: z.string(),
        languages: z.array(z.string()),
        description: z.string(),
      })
      .passthrough()
  ),
});

export const asrHealthResponseSchema = z.object({
  status: z.string(),
  components: healthComponentsSchema,
});

export const nmtModelsListSchema = z.object({
  models: z.array(
    z.object({
      model_id: z.string(),
      provider: z.string(),
      supported_languages: z.array(z.string()),
      description: z.string(),
      max_batch_size: z.number(),
      supported_scripts: z.array(z.string()),
    })
  ),
  total_models: z.number(),
});

export const nmtHealthResponseSchema = z.object({
  status: z.string(),
  components: healthComponentsSchema,
});

export const voiceSchema = z
  .object({
    voice_id: z.string(),
    name: z.string(),
    gender: z.string(),
    age: z.union([z.enum(['young', 'adult', 'senior']), z.string()]),
    languages: z.array(z.string()),
    model_id: z.string(),
    sample_rate: z.number(),
    description: z.string().optional(),
    is_active: z.boolean(),
  })
  .passthrough();

export const voiceListResponseSchema = z.object({
  voices: z.array(voiceSchema),
  total: z.number(),
  filtered: z.number(),
});

export const ttsHealthResponseSchema = z.object({
  status: z.string(),
  components: healthComponentsSchema,
});

export const llmModelsListSchema = z.object({
  models: z.array(
    z
      .object({
        model_id: z.string(),
        provider: z.string(),
        description: z.string(),
        max_batch_size: z.number(),
        supported_languages: z.array(z.string()),
      })
      .passthrough()
  ),
  total_models: z.number(),
});

export const llmHealthResponseSchema = z
  .object({
    status: z.string(),
    service: z.string(),
    version: z.string(),
    redis: z.string(),
    postgres: z.string(),
    triton: z.string(),
    timestamp: z.number(),
  })
  .passthrough();

/** Generic JSON config blob from inference services. */
export const inferenceConfigJsonSchema = z.record(z.unknown());
