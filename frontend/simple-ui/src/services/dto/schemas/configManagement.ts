import { z } from "zod";

/** Platform-core config row. `data` is free-form JSON whose shape depends on `type`. */
export const configItemSchema = z
  .object({
    id: z.string(),
    type: z.string(),
    data: z.record(z.unknown()),
  })
  .passthrough();

/** GET /api/v1/configs */
export const configListResponseSchema = z.object({
  success: z.boolean(),
  data: z.object({
    items: z.array(configItemSchema),
    total: z.number().optional(),
  }),
});

/** `data` of the `domains` config: domain codes in display order. */
export const domainsConfigDataSchema = z.object({
  allowed: z.array(z.string()),
});

export type ConfigItem = z.infer<typeof configItemSchema>;
