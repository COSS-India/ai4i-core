import { z } from 'zod';

export const tenantStatusSchema = z.enum(['PENDING', 'ACTIVE', 'SUSPENDED', 'DEACTIVATED']);

export const tenantViewSchema = z
  .object({
    tenant_id: z.coerce.string(),
    contact_name: z.string(),
    organisation: z.string(),
    email: z.string(),
    phone_number: z.string().nullable().optional(),
    status: tenantStatusSchema,
    created_at: z.string(),
    created_by: z.coerce.string().nullable().optional(),
    updated_at: z.string().nullable().optional(),
    updated_by: z.coerce.string().nullable().optional(),
  })
  .passthrough();

export const tenantUserViewSchema = z
  .object({
    user_id: z.string(),
    username: z.string(),
    email: z.string(),
    phone_number: z.string().nullable().optional(),
    full_name: z.string().nullable().optional(),
    is_active: z.boolean(),
    is_tenant_active: z.boolean().optional(),
    creation_type: z.string().nullable().optional(),
  })
  .passthrough();

export const userRegisterResponseSchema = z.object({
  user_id: z.string(),
  setup_token: z.string(),
  message: z.string(),
});

export const tenantSuccessEnvelopeSchema = <T extends z.ZodTypeAny>(dataSchema: T) =>
  z.object({
    success: z.boolean(),
    data: dataSchema,
    meta: z.record(z.unknown()).optional(),
  });

export const tenantDeleteUserDataSchema = z.object({
  user_id: z.string(),
  deleted: z.boolean(),
});
