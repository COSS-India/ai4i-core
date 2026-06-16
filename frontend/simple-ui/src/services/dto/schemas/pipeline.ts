import { z } from 'zod';

export const pipelineInferenceResponseSchema = z.object({
  pipelineResponse: z.array(
    z
      .object({
        taskType: z.string(),
        serviceId: z.string(),
        output: z.array(z.unknown()).optional(),
        audio: z.array(z.unknown()).optional(),
        config: z.unknown().optional(),
      })
      .passthrough()
  ),
});

export const pipelineInfoOrHealthSchema = z.record(z.unknown());
