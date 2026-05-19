import { z, type ZodTypeAny } from 'zod';
import { unwrapAuthV2Payload } from './unwrap';

/** Validate payload after stripping auth-service `{ success, data }` when present. */
export function authUnwrappedSchema<T extends ZodTypeAny>(inner: T) {
  return z.preprocess((raw: unknown) => unwrapAuthV2Payload(raw), inner);
}
