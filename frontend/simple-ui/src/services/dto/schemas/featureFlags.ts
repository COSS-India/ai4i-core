import { z } from 'zod';

const flagValueSchema = z.union([
  z.boolean(),
  z.string(),
  z.number(),
  z.record(z.unknown()),
]);

export const featureFlagEvaluationResponseSchema = z.object({
  flag_name: z.string(),
  value: flagValueSchema,
  variant: z.string().optional(),
  reason: z.string(),
  evaluated_at: z.string(),
});

export const featureFlagBooleanEvalSchema = z.object({
  flag_name: z.string(),
  value: z.boolean(),
  reason: z.string(),
});

export const featureFlagBulkEvalSchema = z.object({
  results: z.record(z.string(), featureFlagEvaluationResponseSchema),
});

export const featureFlagResponseSchema = z
  .object({
    name: z.string(),
    description: z.string().optional(),
    is_enabled: z.boolean(),
    environment: z.string(),
    rollout_percentage: z.string().optional(),
    target_users: z.array(z.string()).optional(),
    unleash_flag_name: z.string().optional(),
    last_synced_at: z.string().optional(),
    created_at: z.string().optional(),
    updated_at: z.string().optional(),
  })
  .passthrough();

export const featureFlagListResponseSchema = z.object({
  items: z.array(featureFlagResponseSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});

export const featureFlagSyncResponseSchema = z.object({
  synced_count: z.number(),
  environment: z.string(),
});
