import { z } from 'zod';

export const messageResponseSchema = z.object({
  message: z.string(),
});

export const resetPasswordResponseSchema = z.object({
  message: z.string(),
  sign_out_other_sessions: z.boolean().optional(),
});

export const registerResponseSchema = z.object({
  id: z.coerce.number(),
  email: z.string(),
  username: z.string(),
  message: z.string(),
});

export const userSchema = z
  .object({
    user_id: z.string(),
    email: z.string(),
    username: z.string(),
    timezone: z.string(),
    is_active: z.boolean(),
    created_at: z.string(),
  })
  .passthrough();

export const loginResponseSchema = z
  .object({
    access_token: z.string(),
    refresh_token: z.string(),
    token_type: z.string(),
    expires_in: z.number(),
    user: userSchema.optional(),
  })
  .passthrough();

export const tokenRefreshResponseSchema = z.object({
  access_token: z.string(),
  token_type: z.string(),
  expires_in: z.number(),
});

export const tokenValidationResponseSchema = z
  .object({
    valid: z.boolean(),
    permission_ids: z.array(z.number()),
    permissions: z.array(z.string()),
    roles: z.array(z.string()),
    user_id: z.string().optional(),
    username: z.string().optional(),
    tenant_id: z.string().optional(),
    token_type: z.string().optional(),
  })
  .passthrough();

export const logoutResponseSchema = z.object({
  message: z.string(),
  logged_out: z.boolean(),
});

export const setPasswordStatusResponseSchema = z.object({
  valid: z.boolean(),
  status: z.enum(['valid', 'expired', 'invalid', 'used']),
  message: z.string(),
});

const apiKeyResponseRawSchema = z
  .object({
    id: z.coerce.number().optional(),
    key_id: z.coerce.number().optional(),
    key_name: z.string(),
    api_key: z.string().optional(),
    permissions: z.array(z.coerce.number()),
    is_active: z.boolean(),
    is_revoked: z.boolean(),
    created_at: z.string(),
    expires_at: z.string().optional(),
    last_used: z.string().optional(),
  })
  .passthrough();

export const apiKeyResponseSchema = apiKeyResponseRawSchema
  .refine((d) => d.id != null || d.key_id != null, {
    message: 'API key response must include id or key_id',
  })
  .transform((d) => ({
    ...d,
    id: (d.id ?? d.key_id) as number,
  }));

export const apiKeyListUnionSchema = z.union([
  z.array(apiKeyResponseSchema),
  z.object({ api_keys: z.array(apiKeyResponseSchema) }),
]);

export const adminApiKeyWithUserSchema = apiKeyResponseRawSchema
  .extend({
    user_id: z.string(),
    user_email: z.string(),
    username: z.string(),
  })
  .refine((d) => d.id != null || d.key_id != null, {
    message: 'API key response must include id or key_id',
  })
  .transform((d) => ({
    ...d,
    id: (d.id ?? d.key_id) as number,
  }));

export const oauth2ProviderSchema = z.object({
  provider: z.string(),
  client_id: z.string(),
  authorization_url: z.string(),
  scope: z.array(z.string()),
});

export const permissionSchema = z
  .object({
    id: z.coerce.number(),
    name: z.string(),
    resource: z.string(),
    action: z.string(),
    created_at: z.string(),
  })
  .passthrough();

export const guestServicesListSchema = z.array(z.record(z.unknown()));
