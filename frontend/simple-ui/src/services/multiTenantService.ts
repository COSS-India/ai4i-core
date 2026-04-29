// Multi-tenant admin API client (list, view, register, update tenants and users)

import { apiClient } from './api';
import { apiEndpoints } from './apiEndpoints';
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

const mt = apiEndpoints['multi-tenant'];
const mtAdmin = mt.admin;

/**
 * List all tenants in the system (admin).
 * GET mtAdmin.listTenants
 */
export async function listTenants(): Promise<ListTenantsResponse> {
  const { data } = await apiClient.get<ListTenantsResponse>(mtAdmin.listTenants);
  return data;
}

/**
 * List users for one tenant. Backend requires `tenant_id` query param; TENANT ADMIN may only request their own tenant.
 * GET mtAdmin.listUsers
 * @param tenant_id - Tenant to list (logged-in tenant admin: use `user.tenant_id` from auth/me; platform admin: pass selected tenant).
 */
export async function listUsers(tenant_id: string): Promise<ListUsersResponse> {
  const params = { tenant_id };
  const { data } = await apiClient.get<ListUsersResponse>(mtAdmin.listUsers, { params });
  return data;
}

/**
 * View tenant details by tenant_id.
 * GET mtAdmin.viewTenant
 */
export async function getViewTenant(tenant_id: string): Promise<TenantView> {
  const { data } = await apiClient.get<TenantView>(mtAdmin.viewTenant, { params: { tenant_id } });
  return data;
}

/**
 * View tenant user details by user_id.
 * GET mtAdmin.viewUser
 */
export async function getViewUser(user_id: number): Promise<TenantUserView> {
  const { data } = await apiClient.get<TenantUserView>(mtAdmin.viewUser, { params: { user_id } });
  return data;
}

/**
 * Update a tenant's status.
 * PATCH mtAdmin.updateTenantsStatus
 */
export async function updateTenantStatus(payload: TenantStatusUpdateRequest): Promise<TenantStatusUpdateResponse> {
  const { data } = await apiClient.patch<TenantStatusUpdateResponse>(mtAdmin.updateTenantsStatus, payload);
  return data;
}

/**
 * Update a tenant user's status.
 * PATCH mtAdmin.updateUsersStatus
 */
export async function updateUserStatus(payload: TenantUserStatusUpdateRequest): Promise<TenantUserStatusUpdateResponse> {
  const { data } = await apiClient.patch<TenantUserStatusUpdateResponse>(mtAdmin.updateUsersStatus, payload);
  return data;
}

/**
 * Update tenant details. Only passed fields are updated.
 * PATCH mtAdmin.updateTenant
 */
export async function updateTenant(payload: TenantUpdateRequest): Promise<TenantUpdateResponse> {
  const { data } = await apiClient.patch<TenantUpdateResponse>(mtAdmin.updateTenant, payload);
  return data;
}

/**
 * Register a new tenant (organization). Creates tenant record, schema, and sends verification email.
 * POST mtAdmin.registerTenant
 */
export async function registerTenant(payload: TenantRegisterRequest): Promise<TenantRegisterResponse> {
  const { data } = await apiClient.post<TenantRegisterResponse>(mtAdmin.registerTenant, payload);
  return data;
}

/**
 * Register a new user under a tenant. Creates user in both tenant and auth DBs.
 * POST mtAdmin.registerUsers
 */
export async function registerUser(payload: UserRegisterRequest): Promise<UserRegisterResponse> {
  const { data } = await apiClient.post<UserRegisterResponse>(mtAdmin.registerUsers, payload);
  return data;
}

/**
 * Update tenant user (username, email, is_approved). Partial updates.
 * PATCH mtAdmin.updateUser
 */
export async function updateUser(payload: TenantUserUpdateRequest): Promise<TenantUserUpdateResponse> {
  const { data } = await apiClient.patch<TenantUserUpdateResponse>(mtAdmin.updateUser, payload);
  return data;
}

/**
 * Delete a user under a tenant.
 * DELETE mtAdmin.deleteUser
 */
export async function deleteUser(payload: TenantUserDeleteRequest): Promise<TenantUserDeleteResponse> {
  const { data } = await apiClient.delete<TenantUserDeleteResponse>(mtAdmin.deleteUser, { data: payload });
  return data;
}

/**
 * List all registered (active) services.
 * GET mt.listServices
 */
export async function listServices(): Promise<ListServicesResponse> {
  const { data } = await apiClient.get<ListServicesResponse>(mt.listServices);
  return data;
}

/**
 * Add subscriptions to a tenant.
 * POST mt.tenantSubscriptionsAdd
 */
export async function addTenantSubscriptions(payload: TenantSubscriptionAddRequest): Promise<TenantSubscriptionResponse> {
  const { data } = await apiClient.post<TenantSubscriptionResponse>(
    mt.tenantSubscriptionsAdd,
    payload
  );
  return data;
}

/**
 * Remove subscriptions from a tenant.
 * POST mt.tenantSubscriptionsRemove
 */
export async function removeTenantSubscriptions(payload: TenantSubscriptionRemoveRequest): Promise<TenantSubscriptionResponse> {
  const { data } = await apiClient.post<TenantSubscriptionResponse>(
    mt.tenantSubscriptionsRemove,
    payload
  );
  return data;
}

/**
 * Add subscriptions to a tenant user.
 * POST mt.userSubscriptionsAdd
 */
export async function addUserSubscriptions(payload: UserSubscriptionAddRequest): Promise<UserSubscriptionResponse> {
  const { data } = await apiClient.post<UserSubscriptionResponse>(
    mt.userSubscriptionsAdd,
    payload
  );
  return data;
}

/**
 * Remove subscriptions from a tenant user.
 * POST mt.userSubscriptionsRemove
 */
export async function removeUserSubscriptions(payload: UserSubscriptionRemoveRequest): Promise<UserSubscriptionResponse> {
  const { data } = await apiClient.post<UserSubscriptionResponse>(
    mt.userSubscriptionsRemove,
    payload
  );
  return data;
}

/**
 * Send verification email to a tenant. Used for tenants in PENDING status to re-send verification.
 * POST mtAdmin.emailSendVerification
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
    mtAdmin.emailSendVerification,
    { tenant_id }
  );
  return data;
}

/**
 * Resend verification email to a PENDING tenant (new token, same flow as user-facing resend).
 * POST mt.emailResend
 */
export async function resendVerificationEmail(tenant_id: string): Promise<SendVerificationEmailResponse> {
  const { data } = await apiClient.post<SendVerificationEmailResponse>(
    mt.emailResend,
    { tenant_id }
  );
  return data;
}

/**
 * Verify tenant email with token. GET mt.emailVerify?token=...
 */
export async function verifyEmailWithToken(token: string): Promise<{ message: string }> {
  const { data } = await apiClient.get<{ message: string }>(mt.emailVerify, {
    params: { token },
  });
  return data;
}

/**
 * Resolve tenant context from user_id. Used by services to get tenant schema information.
 * GET mt.resolveTenantFromUser/{user_id}
 */
export async function resolveTenantFromUser(user_id: number): Promise<Record<string, unknown>> {
  const { data } = await apiClient.get<Record<string, unknown>>(
    `${mt.resolveTenantFromUser}/${user_id}`
  );
  return data;
}
