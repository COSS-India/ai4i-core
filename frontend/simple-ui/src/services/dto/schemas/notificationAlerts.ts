import { z } from "zod";

/** Platform-core success envelope for notification-alert catalog endpoints. */
export const notificationAlertSuccessEnvelopeSchema = <T extends z.ZodTypeAny>(
  dataSchema: T,
) =>
  z.object({
    success: z.boolean(),
    data: dataSchema,
    meta: z.record(z.unknown()).optional(),
  });

export const catalogItemSchema = z
  .object({
    id: z.number(),
    name: z.string(),
    display_name: z.string(),
    description: z.string(),
    type: z.enum(["NOTIFICATION", "ALERT"]),
    module: z.enum(["TIER", "BUDGET", "QUOTA"]),
    channels: z.array(z.string()).min(1),
    recipient_roles: z.record(z.boolean()),
    thresholds: z.record(z.boolean()).optional().nullable(),
  })
  .passthrough();

export const catalogListDataSchema = z.object({
  items: z.array(catalogItemSchema),
});

export const catalogListResponseSchema =
  notificationAlertSuccessEnvelopeSchema(catalogListDataSchema);

export const catalogUpdateResponseSchema =
  notificationAlertSuccessEnvelopeSchema(catalogItemSchema);

export type ApiCatalogItem = z.infer<typeof catalogItemSchema>;
