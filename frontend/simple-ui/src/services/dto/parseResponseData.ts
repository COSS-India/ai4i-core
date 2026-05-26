import { z, type ZodTypeAny } from 'zod';
import { ApiValidationError } from './apiValidationError';

export function formatZodIssues(issues: z.ZodIssue[]): string {
  return issues.map((e) => `${e.path.length ? e.path.join('.') : '(root)'}: ${e.message}`).join('; ');
}

/**
 * Parse and validate an API JSON body. Throws {@link ApiValidationError} on mismatch.
 */
export function parseResponseData<S extends ZodTypeAny>(
  data: unknown,
  schema: S,
  context?: { method?: string; url?: string }
): z.infer<S> {
  const result = schema.safeParse(data);
  if (!result.success) {
    const detail = formatZodIssues(result.error.issues);
    if (process.env.NODE_ENV === 'development') {
      console.error('[API contract mismatch]', {
        method: context?.method,
        url: context?.url,
        issues: result.error.issues,
        received: data,
      });
    }
    throw new ApiValidationError(`API response validation failed: ${detail}`, result.error.issues, context);
  }
  return result.data;
}
