// Tenant admin API client.
// Backed by auth-service /api/v1/tenants/*.

import { apiClient } from './api';
import type {
  ListTenantsResponse,
  ListUsersResponse,
  TenantRegisterRequest,
  TenantRegisterResponse,
  TenantStatusUpdateRequest,
  TenantStatusUpdateResponse,
  TenantUpdateRequest,
  TenantUpdateResponse,
  TenantUserStatusUpdateRequest,
  TenantUserStatusUpdateResponse,
  TenantUserUpdateRequest,
  TenantUserUpdateResponse,
  TenantUserView,
  TenantView,
  UserRegisterRequest,
  UserRegisterResponse,
} from '../types/tenant';

const BASE = '/api/v1/tenants';

interface Envelope<T> {
  success: boolean;
  data: T;
  meta?: Record<string, unknown>;
}

export async function listTenants(params?: {
  status?: 'activated' | 'deactivated' | 'suspended';
  offset?: number;
  limit?: number;
}): Promise<ListTenantsResponse> {
  const { data } = await apiClient.get<Envelope<TenantView[]>>(BASE, { params });
  const tenants = data.data ?? [];
  return { count: tenants.length, tenants };
}

export async function getViewTenant(tenant_id: string): Promise<TenantView> {
  const { data } = await apiClient.get<Envelope<TenantView>>(`${BASE}/${tenant_id}`);
  return data.data;
}

export async function registerTenant(
  payload: TenantRegisterRequest
): Promise<TenantRegisterResponse> {
  const { data } = await apiClient.post<Envelope<TenantView>>(BASE, payload);
  return data.data;
}

export async function updateTenant(
  payload: TenantUpdateRequest & { tenant_id: string }
): Promise<TenantUpdateResponse> {
  const { tenant_id, ...body } = payload;
  const { data } = await apiClient.patch<Envelope<TenantView>>(
    `${BASE}/${tenant_id}`,
    body
  );
  return data.data;
}

export async function updateTenantStatus(
  payload: TenantStatusUpdateRequest & { tenant_id: string }
): Promise<TenantStatusUpdateResponse> {
  const { tenant_id, status } = payload;
  const { data } = await apiClient.patch<Envelope<TenantView>>(
    `${BASE}/${tenant_id}/status`,
    { status }
  );
  return data.data;
}

export async function listUsers(tenant_id: string): Promise<ListUsersResponse> {
  const { data } = await apiClient.get<Envelope<TenantUserView[]>>(
    `${BASE}/${tenant_id}/users`
  );
  const users = data.data ?? [];
  return { count: users.length, users };
}

export async function getViewUser(user_id: string): Promise<TenantUserView> {
  const { data } = await apiClient.get<Envelope<TenantUserView>>(
    `/api/v1/auth/users/${user_id}`
  );
  return data.data;
}

export async function registerUser(
  payload: UserRegisterRequest & { tenant_id: string }
): Promise<UserRegisterResponse> {
  const { tenant_id, ...body } = payload;
  const { data } = await apiClient.post<Envelope<UserRegisterResponse>>(
    `${BASE}/${tenant_id}/users`,
    body
  );
  return data.data;
}

export async function updateUserStatus(
  payload: TenantUserStatusUpdateRequest & { tenant_id: string; user_id: string }
): Promise<TenantUserStatusUpdateResponse> {
  const { tenant_id, user_id, ...body } = payload;
  const { data } = await apiClient.patch<Envelope<TenantUserView>>(
    `${BASE}/${tenant_id}/users/${user_id}/status`,
    body
  );
  return data.data;
}

export async function updateUser(
  payload: TenantUserUpdateRequest & { tenant_id: string; user_id: string }
): Promise<TenantUserUpdateResponse> {
  const { tenant_id, user_id, ...body } = payload;
  const { data } = await apiClient.patch<Envelope<TenantUserView>>(
    `${BASE}/${tenant_id}/users/${user_id}`,
    body
  );
  return data.data;
}

export async function deleteUser(payload: {
  tenant_id: string;
  user_id: string;
}): Promise<{ user_id: string; deleted: boolean }> {
  const { tenant_id, user_id } = payload;
  const { data } = await apiClient.delete<
    Envelope<{ user_id: string; deleted: boolean }>
  >(`${BASE}/${tenant_id}/users/${user_id}`);
  return data.data;
}
