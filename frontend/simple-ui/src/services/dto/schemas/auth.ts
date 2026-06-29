import { z } from 'zod';
import { SET_PASSWORD_TOKEN } from '../../../constants';

export const messageResponseSchema = z.object({
  message: z.string(),
});

export const checkEmailExistsResponseSchema = z.object({
  exists: z.boolean(),
});

export const resetPasswordResponseSchema = z.object({
  message: z.string(),
  sign_out_other_sessions: z.boolean().optional(),
});

/** POST /auth/register — backend returns `user_id` (UUID string), not numeric `id`. */
export const registerResponseSchema = z.object({
  user_id: z.coerce.string(),
  email: z.string(),
  username: z.string(),
  message: z.string(),
});

/** Full profile from GET /auth/me (and GET /auth/users/{id}). */
export const userSchema = z
  .object({
    user_id: z.string(),
    email: z.string(),
    username: z.string(),
    timezone: z.string().optional(),
    is_active: z.boolean(),
    created_at: z.string().optional(),
  })
  .passthrough();

/** GET /users list items — compact shape (no timezone/created_at). */
export const userListItemSchema = z
  .object({
    user_id: z.coerce.string(),
    email: z.string(),
    username: z.string(),
    is_active: z.boolean(),
    full_name: z.string().nullable().optional(),
    phone_number: z.string().nullable().optional(),
    creation_type: z.string().nullable().optional(),
    is_tenant_active: z.boolean().nullable().optional(),
    roles: z.array(z.string()).optional(),
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
  status: z.preprocess(
    (val) => (typeof val === 'string' ? val.trim().toLowerCase() : val),
    z.enum([
      SET_PASSWORD_TOKEN.STATUS.VALID,
      SET_PASSWORD_TOKEN.STATUS.EXPIRED,
      SET_PASSWORD_TOKEN.STATUS.INVALID,
      SET_PASSWORD_TOKEN.STATUS.USED,
    ])
  ),
  message: z.string(),
});

/** POST /api-keys — raw key shown once; no list metadata. */
export const createApiKeyResponseSchema = z
  .object({
    api_key: z.string(),
    key_name: z.string(),
    permissions: z.array(z.coerce.number()),
    expires_at: z.string().nullable().optional(),
  })
  .passthrough()
  .transform((d) => ({
    ...d,
    expires_at: d.expires_at ?? undefined,
  }));

const apiKeyResponseRawSchema = z
  .object({
    id: z.coerce.number().optional(),
    key_id: z.coerce.number().optional(),
    key_name: z.string(),
    api_key: z.string().optional(),
    user_id: z.string().optional(),
    permissions: z.preprocess(
      (value) => (value == null ? [] : value),
      z.array(z.coerce.number()),
    ),
    is_active: z.boolean().optional(),
    is_revoked: z.boolean().optional(),
    created_at: z.string().nullable().optional(),
    expires_at: z.string().nullable().optional(),
  })
  .passthrough();

function normalizeApiKeyResponse<T extends z.infer<typeof apiKeyResponseRawSchema>>(d: T) {
  const isActive = d.is_active ?? true;
  return {
    ...d,
    ...(d.id != null || d.key_id != null ? { id: (d.id ?? d.key_id) as number } : {}),
    is_active: isActive,
    is_revoked: d.is_revoked ?? !isActive,
    created_at: d.created_at ?? undefined,
    expires_at: d.expires_at ?? undefined,
  };
}

export const apiKeyResponseSchema = apiKeyResponseRawSchema.transform(normalizeApiKeyResponse);

export const apiKeyListResponseSchema = z
  .object({
    api_keys: z.array(apiKeyResponseSchema),
  })
  .passthrough();

/** @deprecated Prefer apiKeyListResponseSchema — kept for legacy array-only payloads. */
export const apiKeyListUnionSchema = z.union([
  z.array(apiKeyResponseSchema),
  apiKeyListResponseSchema,
]);

export const adminApiKeyWithUserSchema = apiKeyResponseRawSchema
  .extend({
    user_id: z.string(),
    user_email: z.string(),
    username: z.string(),
  })
  .transform(normalizeApiKeyResponse);

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

export const permissionListSchema = z.array(permissionSchema);

export const guestServicesListSchema = z.union([
  z.array(z.union([z.string(), z.record(z.unknown())])),
  z.object({
    services: z.array(z.union([z.string(), z.record(z.unknown())])),
  }),
]);
