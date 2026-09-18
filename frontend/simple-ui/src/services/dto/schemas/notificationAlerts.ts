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

/** Mirrors platform-core `ThresholdBand` — no id/name, percentage identifies the band. */
export const thresholdBandSchema = z.object({
  percentage: z.number().int(),
  active: z.boolean(),
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
    /** ALERT rows only — null/omitted on NOTIFICATION rows. */
    thresholds: z.array(thresholdBandSchema).optional().nullable(),
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
export type ApiThresholdBand = z.infer<typeof thresholdBandSchema>;
