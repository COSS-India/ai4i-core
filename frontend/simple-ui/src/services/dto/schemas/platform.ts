import { z } from 'zod';
import { unwrapAuthV2Payload } from '../unwrap';
import { unwrapPlatformDataEnvelope } from '../unwrap';

/** Platform list responses may use `{ success, data }` or `{ data }`. */
function unwrapPlatformListPayload(raw: unknown): unknown {
  return unwrapPlatformDataEnvelope(unwrapAuthV2Payload(raw));
}

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

export const servicesListSchema = z.preprocess((raw: unknown) => {
  let data = unwrapPlatformDataEnvelope(raw);
  // API wraps the service list under { services: [...] }
  if (data && typeof data === 'object' && !Array.isArray(data) && 'services' in data) {
    data = (data as Record<string, unknown>).services;
  }
  return data;
}, z.array(serviceRecordSchema));

export const serviceSingleSchema = withPlatformEnvelope(serviceRecordSchema);

/** Try-it and other callers expect a plain service array. */
export const tryItServiceListSchema = z.preprocess((raw: unknown) => {
  let data = unwrapPlatformListPayload(raw);
  // Response nests services under { services: [...] } — extract to array
  if (data && typeof data === 'object' && !Array.isArray(data) && 'services' in data) {
    data = (data as Record<string, unknown>).services;
  }
  return data;
}, z.array(platformRecordSchema));

export const unknownPlatformPayloadSchema = withPlatformEnvelope(z.unknown());
