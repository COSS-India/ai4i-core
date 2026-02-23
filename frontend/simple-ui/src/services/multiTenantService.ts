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
 * GET /api/v1/multi-tenant/admin/list/tenants
 */
export async function listTenants(): Promise<ListTenantsResponse> {
  const { data } = await apiClient.get<ListTenantsResponse>(`${BASE}/admin/list/tenants`);
  return data;
}

/**
 * List users (optionally filtered by tenant). When tenant_id is passed, only users for that tenant are returned.
 * GET /api/v1/multi-tenant/admin/list/users
 * @param tenant_id - Optional. From /api/v1/auth/me for logged-in tenant; when provided, returns only that tenant's users.
 */
export async function listUsers(tenant_id?: string | null): Promise<ListUsersResponse> {
  const params = tenant_id ? { tenant_id } : {};
  const { data } = await apiClient.get<ListUsersResponse>(`${BASE}/admin/list/users`, { params });
  return data;
}

/**
 * View tenant details by tenant_id.
 * GET /api/v1/multi-tenant/admin/view/tenant
 */
export async function getViewTenant(tenant_id: string): Promise<TenantView> {
  const { data } = await apiClient.get<TenantView>(`${BASE}/admin/view/tenant`, { params: { tenant_id } });
  return data;
}

/**
 * View tenant user details by user_id.
 * GET /api/v1/multi-tenant/admin/view/user
 */
export async function getViewUser(user_id: number): Promise<TenantUserView> {
  const { data } = await apiClient.get<TenantUserView>(`${BASE}/admin/view/user`, { params: { user_id } });
  return data;
}

/**
 * Update a tenant's status.
 * PATCH /api/v1/multi-tenant/admin/update/tenants/status
 */
export async function updateTenantStatus(payload: TenantStatusUpdateRequest): Promise<TenantStatusUpdateResponse> {
  const { data } = await apiClient.patch<TenantStatusUpdateResponse>(`${BASE}/admin/update/tenants/status`, payload);
  return data;
}

/**
 * Update a tenant user's status.
 * PATCH /api/v1/multi-tenant/admin/update/users/status
 */
export async function updateUserStatus(payload: TenantUserStatusUpdateRequest): Promise<TenantUserStatusUpdateResponse> {
  const { data } = await apiClient.patch<TenantUserStatusUpdateResponse>(`${BASE}/admin/update/users/status`, payload);
  return data;
}

/**
 * Update tenant details. Only passed fields are updated.
 * PATCH /api/v1/multi-tenant/admin/update/tenant
 */
export async function updateTenant(payload: TenantUpdateRequest): Promise<TenantUpdateResponse> {
  const { data } = await apiClient.patch<TenantUpdateResponse>(`${BASE}/admin/update/tenant`, payload);
  return data;
}

/**
 * Register a new tenant (organization). Creates tenant record, schema, and sends verification email.
 * POST /api/v1/multi-tenant/admin/register/tenant
 */
export async function registerTenant(payload: TenantRegisterRequest): Promise<TenantRegisterResponse> {
  const { data } = await apiClient.post<TenantRegisterResponse>(`${BASE}/admin/register/tenant`, payload);
  return data;
}

/**
 * Register a new user under a tenant. Creates user in both tenant and auth DBs.
 * POST /api/v1/multi-tenant/admin/register/users
 */
export async function registerUser(payload: UserRegisterRequest): Promise<UserRegisterResponse> {
  const { data } = await apiClient.post<UserRegisterResponse>(`${BASE}/admin/register/users`, payload);
  return data;
}

/**
 * Update tenant user (username, email, is_approved). Partial updates.
 * PATCH /api/v1/multi-tenant/admin/update/user
 */
export async function updateUser(payload: TenantUserUpdateRequest): Promise<TenantUserUpdateResponse> {
  const { data } = await apiClient.patch<TenantUserUpdateResponse>(`${BASE}/admin/update/user`, payload);
  return data;
}

/**
 * Delete a user under a tenant.
 * DELETE /api/v1/multi-tenant/admin/delete/user
 */
export async function deleteUser(payload: TenantUserDeleteRequest): Promise<TenantUserDeleteResponse> {
  const { data } = await apiClient.delete<TenantUserDeleteResponse>(`${BASE}/admin/delete/user`, { data: payload });
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
 * Add subscriptions to a tenant.
 * POST /api/v1/multi-tenant/tenant/subscriptions/add
 */
export async function addTenantSubscriptions(payload: TenantSubscriptionAddRequest): Promise<TenantSubscriptionResponse> {
  const { data } = await apiClient.post<TenantSubscriptionResponse>(`${BASE}/tenant/subscriptions/add`, payload);
  return data;
}

/**
 * Remove subscriptions from a tenant.
 * POST /api/v1/multi-tenant/tenant/subscriptions/remove
 */
export async function removeTenantSubscriptions(payload: TenantSubscriptionRemoveRequest): Promise<TenantSubscriptionResponse> {
  const { data } = await apiClient.post<TenantSubscriptionResponse>(`${BASE}/tenant/subscriptions/remove`, payload);
  return data;
}

/**
 * Add subscriptions to a tenant user.
 * POST /api/v1/multi-tenant/user/subscriptions/add
 */
export async function addUserSubscriptions(payload: UserSubscriptionAddRequest): Promise<UserSubscriptionResponse> {
  const { data } = await apiClient.post<UserSubscriptionResponse>(`${BASE}/user/subscriptions/add`, payload);
  return data;
}

/**
 * Remove subscriptions from a tenant user.
 * POST /api/v1/multi-tenant/user/subscriptions/remove
 */
export async function removeUserSubscriptions(payload: UserSubscriptionRemoveRequest): Promise<UserSubscriptionResponse> {
  const { data } = await apiClient.post<UserSubscriptionResponse>(`${BASE}/user/subscriptions/remove`, payload);
  return data;
}

/**
 * Send verification email to a tenant. Used for tenants in PENDING status to re-send verification.
 * POST /api/v1/multi-tenant/admin/email/send/verification
 * Returns the full response including token (for use in verify flow).
 */
export interface SendVerificationEmailResponse {
  tenant_uuid: string;
  tenant_id: string;
  token: string;
  message: string;
}

export async function sendVerificationEmail(tenant_id: string): Promise<SendVerificationEmailResponse> {
  const { data } = await apiClient.post<SendVerificationEmailResponse>(
    `${BASE}/admin/email/send/verification`,
    { tenant_id }
  );
  return data;
}

/**
 * Verify tenant email with token. GET /api/v1/multi-tenant/email/verify?token=...
 */
export async function verifyEmailWithToken(token: string): Promise<{ message: string }> {
  const { data } = await apiClient.get<{ message: string }>(`${BASE}/email/verify`, {
    params: { token },
  });
  return data;
}

/**
 * Resolve tenant context from user_id. Used by services to get tenant schema information.
 * GET /api/v1/multi-tenant/resolve/tenant/from/user/{user_id}
 */
export async function resolveTenantFromUser(user_id: number): Promise<Record<string, unknown>> {
  const { data } = await apiClient.get<Record<string, unknown>>(
    `${BASE}/resolve/tenant/from/user/${user_id}`
  );
  return data;
}
