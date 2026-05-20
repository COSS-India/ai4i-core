import { z } from 'zod';

const healthComponentsSchema = z.record(
  z.string(),
  z
    .object({
      status: z.string(),
      details: z.unknown().optional(),
    })
    .passthrough()
);

export const asrInferenceResponseSchema = z.object({
  output: z.array(
    z
      .object({
        source: z.string(),
        nBestTokens: z.unknown().optional(),
      })
      .passthrough()
  ),
});

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

export const nmtInferenceResponseSchema = z.object({
  output: z.array(
    z.object({
      source: z.string(),
      target: z.string(),
    })
  ),
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

export const ttsInferenceResponseSchema = z
  .object({
    audio: z.array(
      z
        .object({
          audioContent: z.string(),
          audioUri: z.string().optional(),
        })
        .passthrough()
    ),
    config: z.record(z.unknown()).optional(),
  })
  .passthrough();

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

export const llmInferenceResponseSchema = z.object({
  output: z.array(
    z.object({
      source: z.string(),
      target: z.string(),
    })
  ),
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

export const ocrInferenceResponseSchema = z.object({
  output: z.array(
    z
      .object({
        source: z.string(),
      })
      .passthrough()
  ),
});

export const nerInferenceResponseSchema = z.object({
  output: z.array(
    z
      .object({
        source: z.string(),
        entities: z
          .array(
            z.object({
              text: z.string(),
              label: z.string(),
              start: z.number(),
              end: z.number(),
            })
          )
          .optional(),
      })
      .passthrough()
  ),
});

export const languageDetectionInferenceResponseSchema = z.object({
  output: z.array(
    z
      .object({
        source: z.string(),
        langPrediction: z.array(
          z.object({
            langCode: z.string(),
            scriptCode: z.string(),
            langScore: z.number(),
            language: z.string(),
          })
        ),
      })
      .passthrough()
  ),
});

export const transliterationInferenceResponseSchema = z.object({
  output: z.array(
    z
      .object({
        source: z.string(),
        target: z.string(),
      })
      .passthrough()
  ),
});

export const speakerDiarizationInferenceResponseSchema = z.object({
  output: z.array(
    z
      .object({
        segments: z
          .array(
            z.object({
              start: z.number(),
              end: z.number(),
              speaker: z.string(),
              text: z.string().optional(),
            })
          )
          .optional(),
      })
      .passthrough()
  ),
});

export const languageDiarizationInferenceResponseSchema = z.object({
  output: z.array(
    z
      .object({
        segments: z
          .array(
            z.object({
              start: z.number(),
              end: z.number(),
              language: z.string(),
            })
          )
          .optional(),
      })
      .passthrough()
  ),
});

export const audioLanguageDetectionInferenceResponseSchema = z.object({
  output: z.array(
    z
      .object({
        detectedLanguage: z.string().optional(),
        confidence: z.number().optional(),
      })
      .passthrough()
  ),
});

/** Generic JSON config blob from inference services. */
export const inferenceConfigJsonSchema = z.record(z.unknown());
