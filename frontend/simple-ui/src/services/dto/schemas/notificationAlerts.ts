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
    scope: z.enum(["GLOBAL", "INSTITUTION"]),
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

/**
 * Mirrors platform-core `SubscriptionItem`. `description`/`thresholds` are
 * optional so the UI keeps working before the BE starts sending them.
 */
export const subscriptionItemSchema = z
  .object({
    notification_id: z.number(),
    name: z.string(),
    display_name: z.string(),
    description: z.string().optional().nullable(),
    scope: z.enum(["GLOBAL", "INSTITUTION"]),
    delivery_channel: z.array(z.string()),
    subscribed: z.boolean(),
    locked: z.boolean(),
    recipients: z.array(z.string()),
    thresholds: z.array(thresholdBandSchema).optional().nullable(),
  })
  .passthrough();

export const subscriptionListResponseSchema = notificationAlertSuccessEnvelopeSchema(
  z.object({ items: z.array(subscriptionItemSchema) }),
);

export const subscriptionUpdateResponseSchema =
  notificationAlertSuccessEnvelopeSchema(subscriptionItemSchema);

export type ApiSubscriptionItem = z.infer<typeof subscriptionItemSchema>;
