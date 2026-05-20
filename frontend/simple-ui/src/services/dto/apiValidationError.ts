import type { ZodIssue } from 'zod';

export class ApiValidationError extends Error {
  readonly issues: ZodIssue[];

  readonly context?: { method?: string; url?: string };

  constructor(message: string, issues: ZodIssue[], context?: { method?: string; url?: string }) {
    super(message);
    this.name = 'ApiValidationError';
    this.issues = issues;
    this.context = context;
  }
}
