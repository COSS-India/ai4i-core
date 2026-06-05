// Tenant admin API client.
// Backed by auth-service tenant endpoints.

import { z } from 'zod';
import { apiService } from './api';
import { apiEndpoints } from './apiEndpoints';
import {
  tenantDeleteUserDataSchema,
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

export async function listTenants(params?: {
  status?: TenantStatus;
  offset?: number;
  limit?: number;
}): Promise<ListTenantsResponse> {
  const response = await apiService.get(BASE, {
    params,
    responseSchema: tenantSuccessEnvelopeSchema(z.array(tenantViewSchema)),
  });
  const tenants = response.data.data ?? [];
  return { count: tenants.length, tenants };
}

export async function getViewTenant(tenant_id: string): Promise<TenantView> {
  const response = await apiService.get(`${BASE}/${tenant_id}`, {
    responseSchema: tenantSuccessEnvelopeSchema(tenantViewSchema),
  });
  return response.data.data;
}

export async function registerTenant(
  payload: TenantRegisterRequest
): Promise<TenantRegisterResponse> {
  const response = await apiService.post(BASE, payload, {
    responseSchema: tenantSuccessEnvelopeSchema(tenantViewSchema),
  });
  return response.data.data;
}

export async function updateTenant(
  payload: TenantUpdateRequest & { tenant_id: string }
): Promise<TenantUpdateResponse> {
  const { tenant_id, ...body } = payload;
  const response = await apiService.patch(`${BASE}/${tenant_id}`, body, {
    responseSchema: tenantSuccessEnvelopeSchema(tenantViewSchema),
  });
  return response.data.data;
}

export async function updateTenantStatus(
  payload: TenantStatusUpdateRequest & { tenant_id: string }
): Promise<TenantStatusUpdateResponse> {
  const { tenant_id, status } = payload;
  const response = await apiService.patch(`${BASE}/${tenant_id}/status`, { status }, {
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
      responseSchema: tenantSuccessEnvelopeSchema(
        z.object({ message: z.string() }).passthrough()
      ),
    }
  );
  const data = response.data.data as { message?: string };
  return { message: data?.message ?? "Verification email sent." };
}

export async function listUsers(tenant_id: string): Promise<ListUsersResponse> {
  const response = await apiService.get(`${BASE}/${tenant_id}/users`, {
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
    responseSchema: tenantSuccessEnvelopeSchema(tenantDeleteUserDataSchema),
  });
  return response.data.data;
}
