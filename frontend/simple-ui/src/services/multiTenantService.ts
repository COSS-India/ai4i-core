// Multi-tenant admin API client (list, view, register, update tenants and users)

import { apiClient } from './api';
import type {
  ListTenantsResponse,
  ListUsersResponse,
  ListServicesResponse,
  TenantRegisterRequest,
  TenantRegisterResponse,
  UserRegisterRequest,
  UserRegisterResponse,
  TenantView,
  TenantUserView,
  TenantStatusUpdateRequest,
  TenantStatusUpdateResponse,
  TenantUserStatusUpdateRequest,
  TenantUserStatusUpdateResponse,
  TenantUpdateRequest,
  TenantUpdateResponse,
  TenantUserUpdateRequest,
  TenantUserUpdateResponse,
  TenantUserDeleteRequest,
  TenantUserDeleteResponse,
  TenantSubscriptionAddRequest,
  TenantSubscriptionRemoveRequest,
  TenantSubscriptionResponse,
  UserSubscriptionAddRequest,
  UserSubscriptionRemoveRequest,
  UserSubscriptionResponse,
} from '../types/multiTenant';

const BASE = '/api/v1/multi-tenant';

/**
 * List all tenants in the system (admin).
 * Note: The admin router has prefix "/admin", so the endpoint is "/admin/list/tenants"
 */
export async function listTenants(): Promise<ListTenantsResponse> {
  try {
    // The admin router has prefix "/admin", so we need "/admin/list/tenants"
    // If BASE is "/api/v1/multi-tenant", the full path becomes "/api/v1/multi-tenant/admin/list/tenants"
    const { data } = await apiClient.get<ListTenantsResponse>(`${BASE}/admin/list/tenants`);
    return data;
  } catch (error: any) {
    console.error('Error in listTenants service call:', {
      error,
      message: error?.message,
      response: error?.response?.data,
      status: error?.response?.status,
      url: error?.config?.url,
    });
    throw error;
  }
}

/**
 * List all users across tenants in the system (admin).
 */
export async function listUsers(): Promise<ListUsersResponse> {
  const { data } = await apiClient.get<ListUsersResponse>(`${BASE}/list/users`);
  return data;
}

/**
 * View tenant details by tenant_id (GET /admin/view/tenant).
 */
export async function getViewTenant(tenant_id: string): Promise<TenantView> {
  const { data } = await apiClient.get<TenantView>(`${BASE}/view/tenant`, { params: { tenant_id } });
  return data;
}

/**
 * View tenant user details by user_id (GET /admin/view/user).
 */
export async function getViewUser(user_id: number): Promise<TenantUserView> {
  const { data } = await apiClient.get<TenantUserView>(`${BASE}/view/user`, { params: { user_id } });
  return data;
}

/**
 * Update a tenant's status (PATCH /admin/update/tenants/status).
 */
export async function updateTenantStatus(payload: TenantStatusUpdateRequest): Promise<TenantStatusUpdateResponse> {
  const { data } = await apiClient.patch<TenantStatusUpdateResponse>(`${BASE}/update/tenants/status`, payload);
  return data;
}

/**
 * Update a tenant user's status (PATCH /admin/update/users/status).
 */
export async function updateUserStatus(payload: TenantUserStatusUpdateRequest): Promise<TenantUserStatusUpdateResponse> {
  const { data } = await apiClient.patch<TenantUserStatusUpdateResponse>(`${BASE}/update/users/status`, payload);
  return data;
}

/**
 * Update tenant details (PATCH /admin/update/tenant). Only passed fields are updated.
 */
export async function updateTenant(payload: TenantUpdateRequest): Promise<TenantUpdateResponse> {
  const { data } = await apiClient.patch<TenantUpdateResponse>(`${BASE}/update/tenant`, payload);
  return data;
}

/**
 * Register a new tenant (organization). Creates tenant record, schema, and sends verification email.
 */
export async function registerTenant(payload: TenantRegisterRequest): Promise<TenantRegisterResponse> {
  const { data } = await apiClient.post<TenantRegisterResponse>(`${BASE}/register/tenant`, payload);
  return data;
}

/**
 * Register a new user under a tenant. Creates user in both tenant and auth DBs.
 */
export async function registerUser(payload: UserRegisterRequest): Promise<UserRegisterResponse> {
  const { data } = await apiClient.post<UserRegisterResponse>(`${BASE}/register/users`, payload);
  return data;
}

/**
 * Update tenant user (username, email, is_approved). PATCH /admin/update/user. Partial updates.
 */
export async function updateUser(payload: TenantUserUpdateRequest): Promise<TenantUserUpdateResponse> {
  const { data } = await apiClient.patch<TenantUserUpdateResponse>(`${BASE}/update/user`, payload);
  return data;
}

/**
 * Delete a user under a tenant. DELETE /admin/delete/user.
 */
export async function deleteUser(payload: TenantUserDeleteRequest): Promise<TenantUserDeleteResponse> {
  const { data } = await apiClient.delete<TenantUserDeleteResponse>(`${BASE}/delete/user`, { data: payload });
  return data;
}

/**
 * List all registered (active) services. GET /list/services.
 */
export async function listServices(): Promise<ListServicesResponse> {
  const { data } = await apiClient.get<ListServicesResponse>(`${BASE}/list/services`);
  return data;
}

/**
 * Add subscriptions to a tenant. POST /tenant/subscriptions/add.
 */
export async function addTenantSubscriptions(payload: TenantSubscriptionAddRequest): Promise<TenantSubscriptionResponse> {
  const { data } = await apiClient.post<TenantSubscriptionResponse>(`${BASE}/subscriptions/add`, payload);
  return data;
}

/**
 * Remove subscriptions from a tenant. POST /tenant/subscriptions/remove.
 */
export async function removeTenantSubscriptions(payload: TenantSubscriptionRemoveRequest): Promise<TenantSubscriptionResponse> {
  const { data } = await apiClient.post<TenantSubscriptionResponse>(`${BASE}/subscriptions/remove`, payload);
  return data;
}

/**
 * Add subscriptions to a tenant user. POST /user/subscriptions/add.
 */
export async function addUserSubscriptions(payload: UserSubscriptionAddRequest): Promise<UserSubscriptionResponse> {
  const { data } = await apiClient.post<UserSubscriptionResponse>(`${BASE}/user/subscriptions/add`, payload);
  return data;
}

/**
 * Remove subscriptions from a tenant user. POST /user/subscriptions/remove.
 */
export async function removeUserSubscriptions(payload: UserSubscriptionRemoveRequest): Promise<UserSubscriptionResponse> {
  const { data } = await apiClient.post<UserSubscriptionResponse>(`${BASE}/user/subscriptions/remove`, payload);
  return data;
}

/**
 * Send verification email to a tenant. POST /admin/email/send/verification.
 * Used for tenants in PENDING status to re-send verification.
 */
export async function sendVerificationEmail(tenant_id: string): Promise<{ message: string }> {
  const { data } = await apiClient.post<{ message: string }>(`${BASE}/email/send-verification`, { tenant_id });
  return data;
}
