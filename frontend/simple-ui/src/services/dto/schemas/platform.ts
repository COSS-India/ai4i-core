import { z } from 'zod';
import { unwrapPlatformDataEnvelope } from '../unwrap';

/** Single platform record (models / services) — passthrough for evolving API fields. */
export const platformRecordSchema = z.object({}).passthrough();

export const modelDetailsSchema = platformRecordSchema;

export const serviceRecordSchema = platformRecordSchema;

export const unpublishModelResponseSchema = z.object({
  message: z.string(),
  modelId: z.string(),
  success: z.boolean(),
});

/** Preprocess: unwrap `{ data?: T }` or return raw array/object. */
export function withPlatformEnvelope<T extends z.ZodTypeAny>(inner: T) {
  return z.preprocess((raw: unknown) => unwrapPlatformDataEnvelope(raw), inner);
}

export const modelsListSchema = withPlatformEnvelope(z.array(modelDetailsSchema));

export const modelSingleSchema = withPlatformEnvelope(modelDetailsSchema);

export const servicesListSchema = withPlatformEnvelope(z.array(serviceRecordSchema));

export const serviceSingleSchema = withPlatformEnvelope(serviceRecordSchema);

/** Try-it and other callers expect a plain service array. */
export const tryItServiceListSchema = z.preprocess(
  (raw: unknown) => unwrapPlatformDataEnvelope(raw),
  z.array(platformRecordSchema)
);

export const unknownPlatformPayloadSchema = withPlatformEnvelope(z.unknown());
