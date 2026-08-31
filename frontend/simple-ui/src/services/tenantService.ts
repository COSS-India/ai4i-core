// Tenant admin API client.
// Backed by auth-service tenant endpoints.

import { z } from 'zod';
import { apiService } from './api';
import { apiEndpoints } from './apiEndpoints';
import {
  tenantDeleteUserDataSchema,
  tenantCreateResponseSchema,
  tenantListDataSchema,
  tenantSuccessEnvelopeSchema,
  tenantUserViewSchema,
  tenantViewSchema,
  userRegisterResponseSchema,
} from './dto/schemas/tenant';
import type {
  ListTenantsResponse,
  ListUsersResponse,
  TenantRegisterRequest,
  TenantRegisterResponse,
  TenantStatus,
  TenantStatusUpdateRequest,
  TenantStatusUpdateResponse,
  TenantUpdateRequest,
  TenantUpdateResponse,
  TenantUserStatusUpdateRequest,
  TenantUserStatusUpdateResponse,
  TenantUserUpdateRequest,
  TenantUserUpdateResponse,
  TenantView,
  UserRegisterRequest,
  UserRegisterResponse,
} from '../types/tenant';

const BASE = apiEndpoints.tenants.base;

function unwrapTenantView(payload: unknown): TenantView {
  const parsed = tenantCreateResponseSchema.parse(payload);
  if (
    parsed &&
    typeof parsed === "object" &&
    "data" in parsed &&
    parsed.data &&
    typeof parsed.data === "object"
  ) {
    return tenantViewSchema.parse(parsed.data);
  }
  return tenantViewSchema.parse(parsed);
}

export async function listTenants(params?: {
  status?: TenantStatus;
  offset?: number;
  limit?: number;
}): Promise<ListTenantsResponse> {
  const response = await apiService.get(BASE, {
    params,
    suppressErrorAlert: true,
    responseSchema: z.union([
      tenantSuccessEnvelopeSchema(z.array(tenantViewSchema)),
      tenantListDataSchema,
    ]),
  });
  const root = response.data as { data?: TenantView[] };
  const tenants = Array.isArray(root?.data) ? root.data : [];
  return { count: tenants.length, tenants };
}

export async function getViewTenant(
  tenant_id: string,
  opts?: { unmask?: boolean }
): Promise<TenantView> {
  const response = await apiService.get(`${BASE}/${tenant_id}`, {
    params: opts?.unmask ? { unmask: true } : undefined,
    suppressErrorAlert: true,
    responseSchema: tenantSuccessEnvelopeSchema(tenantViewSchema),
  });
  return response.data.data;
}

export async function registerTenant(
  payload: TenantRegisterRequest
): Promise<TenantRegisterResponse> {
  const response = await apiService.post(BASE, payload, {
    suppressErrorAlert: true,
    responseSchema: tenantCreateResponseSchema,
  });
  return unwrapTenantView(response.data);
}

export async function updateTenant(
  payload: TenantUpdateRequest & { tenant_id: string }
): Promise<TenantUpdateResponse> {
  const { tenant_id, ...body } = payload;
  const response = await apiService.patch(`${BASE}/${tenant_id}`, body, {
    suppressErrorAlert: true,
    responseSchema: tenantSuccessEnvelopeSchema(tenantViewSchema),
  });
  return response.data.data;
}

export async function updateTenantStatus(
  payload: TenantStatusUpdateRequest & { tenant_id: string }
): Promise<TenantStatusUpdateResponse> {
  const { tenant_id, status } = payload;
  const response = await apiService.patch(`${BASE}/${tenant_id}/status`, { status }, {
    suppressErrorAlert: true,
    responseSchema: tenantSuccessEnvelopeSchema(tenantViewSchema),
  });
  return response.data.data;
}

/**
 * Re-send verification email to the tenant contact (PENDING tenants).
 * Wire up in useTenantManagement once auth-service exposes this route.
 */
export async function resendTenantVerificationEmail(
  tenant_id: string
): Promise<{ message: string }> {
  const response = await apiService.post(
    apiEndpoints.tenants.resendVerification(tenant_id),
    {},
    {
      suppressErrorAlert: true,
      responseSchema: tenantSuccessEnvelopeSchema(
        z.object({ message: z.string() }).passthrough()
      ),
    }
  );
  const data = response.data.data as { message?: string };
  return { message: data?.message ?? "Verification email sent." };
}

/**
 * Re-send the set-password (SETUP) onboarding email to a tenant user.
 * Tenant users are passwordless until they complete the setup link —
 * do not use /auth/resend-verification for them.
 */
export async function resendTenantUserSetupLink(
  tenant_id: string,
  user_id: string
): Promise<{ message: string }> {
  const response = await apiService.post(
    apiEndpoints.tenants.resendUserSetupLink(tenant_id, user_id),
    {},
    {
      suppressErrorAlert: true,
      responseSchema: tenantSuccessEnvelopeSchema(
        z.object({ message: z.string() }).passthrough()
      ),
    }
  );
  const data = response.data.data as { message?: string };
  return {
    message:
      data?.message ??
      "A password setup link has been sent to the user's email.",
  };
}

export async function listUsers(
  tenant_id: string,
  opts?: { unmask?: boolean }
): Promise<ListUsersResponse> {
  const response = await apiService.get(`${BASE}/${tenant_id}/users`, {
    params: opts?.unmask ? { unmask: true } : undefined,
    suppressErrorAlert: true,
    responseSchema: tenantSuccessEnvelopeSchema(z.array(tenantUserViewSchema)),
  });
  const users = response.data.data ?? [];
  return { count: users.length, users };
}

export async function registerUser(
  payload: UserRegisterRequest & { tenant_id: string }
): Promise<UserRegisterResponse> {
  const { tenant_id, ...body } = payload;
  const response = await apiService.post(`${BASE}/${tenant_id}/users`, body, {
    suppressErrorAlert: true,
    responseSchema: tenantSuccessEnvelopeSchema(userRegisterResponseSchema),
  });
  return response.data.data;
}

export async function updateUserStatus(
  payload: TenantUserStatusUpdateRequest & { tenant_id: string; user_id: string }
): Promise<TenantUserStatusUpdateResponse> {
  const { tenant_id, user_id, ...body } = payload;
  const response = await apiService.patch(
    `${BASE}/${tenant_id}/users/${user_id}/status`,
    body,
    {
      suppressErrorAlert: true,
      responseSchema: tenantSuccessEnvelopeSchema(tenantUserViewSchema),
    }
  );
  return response.data.data;
}

export async function updateUser(
  payload: TenantUserUpdateRequest & { tenant_id: string; user_id: string }
): Promise<TenantUserUpdateResponse> {
  const { tenant_id, user_id, ...body } = payload;
  const response = await apiService.patch(`${BASE}/${tenant_id}/users/${user_id}`, body, {
    suppressErrorAlert: true,
    responseSchema: tenantSuccessEnvelopeSchema(tenantUserViewSchema),
  });
  return response.data.data;
}

export async function deleteUser(payload: {
  tenant_id: string;
  user_id: string;
}): Promise<{ user_id: string; deleted: boolean }> {
  const { tenant_id, user_id } = payload;
  const response = await apiService.delete(`${BASE}/${tenant_id}/users/${user_id}`, {
    suppressErrorAlert: true,
    responseSchema: tenantSuccessEnvelopeSchema(tenantDeleteUserDataSchema),
  });
  return response.data.data;
}
