import { z } from "zod";

/** Platform-core config row. `data` is free-form JSON (object, array, …) whose shape depends on `type`. */
export const configItemSchema = z
  .object({
    id: z.number(),
    type: z.string(),
    data: z.unknown(),
  })
  .passthrough();

/** GET /api/v1/config */
export const configListResponseSchema = z.object({
  success: z.boolean(),
  data: z.object({
    items: z.array(configItemSchema),
    total: z.number().optional(),
  }),
});

/** `data` of the `domain` config: domains in display order. */
export const domainsConfigDataSchema = z.array(
  z
    .object({
      key: z.string(),
      label: z.string().optional(),
      required: z.boolean().optional(),
    })
    .passthrough(),
);

export type ConfigItem = z.infer<typeof configItemSchema>;

/** `data` of the `suspend-reasons` / `deactivate-reasons` configs: reasons in display order. */
export const statusReasonsConfigDataSchema = z.array(
  z
    .object({
      key: z.string(),
      label: z.string().optional(),
    })
    .passthrough(),
);

/** `data` of the `model-column` config: Model List columns in display order. */
export const modelColumnsConfigDataSchema = z.array(
  z
    .object({
      key: z.string(),
      label: z.string().optional(),
      required: z.boolean().optional(),
      /** Shown on first visit and after "Reset to default"; omitted → built-in default. */
      defaultVisible: z.boolean().optional(),
    })
    .passthrough(),
);
