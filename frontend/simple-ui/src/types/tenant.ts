// Tenant + tenant-user types — calls auth-service /api/v1/auth/tenants endpoints.

import type { TenantStatusValue, TenantUserStatusValue } from '../config/constants';

export type TenantStatus = TenantStatusValue;
export type TenantUserStatus = TenantUserStatusValue;
export type CreationType = 'direct' | 'google' | 'tenant';

export interface TenantView {
  tenant_id: string; // UUID
  contact_name: string;
  organisation: string;
  email: string;
  phone_number?: string | null;
  status: TenantStatus;
  /** Client-side flag for PENDING → Deactivate soft deletes (terminal). */
  onboarding_completed?: boolean;
  created_at: string;
  created_by?: string | null;
  updated_at?: string | null;
  updated_by?: string | null;
}

export interface ListTenantsResponse {
  count: number;
  tenants: TenantView[];
}

export interface TenantUserView {
  user_id: string; // UUID
  username: string;
  email: string;
  phone_number?: string | null;
  full_name?: string | null;
  is_active: boolean;
  is_tenant_active?: boolean | null;
  /** True once the user completed setup (set a password). Distinguishes a
   * suspended user (is_active=false, activated) from one pending activation. */
  is_activated?: boolean;
  creation_type?: CreationType | null;
  /** Primary role from list-users API (upcoming: singular `role`). */
  role?: string | null;
  /** Role list when API returns `roles[]` (legacy or profile/detail). */
  roles?: string[];
}

export interface ListUsersResponse {
  count: number;
  users: TenantUserView[];
}

// POST /api/v1/auth/tenants
export interface TenantRegisterRequest {
  contact_name: string;
  organisation: string;
  email: string;
  phone_number?: string;
}
export type TenantRegisterResponse = TenantView;

/** Roles assignable to tenant-scoped users (auth-service TenantUserRole). */
export type TenantAssignableRole = "USER" | "TENANT ADMIN";

// POST /api/v1/auth/tenants/{tenant_id}/users
export interface UserRegisterRequest {
  email: string;
  full_name?: string;
  phone_number?: string;
  role?: TenantAssignableRole;
}

export interface UserRegisterResponse {
  user_id: string;
  setup_token: string;
  message: string;
}

// PATCH /api/v1/auth/tenants/{tenant_id}/status
export interface TenantStatusUpdateRequest {
  status: TenantStatus;
}
export type TenantStatusUpdateResponse = TenantView;

// PATCH /api/v1/auth/tenants/{tenant_id}/users/{user_id}/status
export interface TenantUserStatusUpdateRequest {
  is_active?: boolean;
  is_tenant_active?: boolean;
}
export type TenantUserStatusUpdateResponse = TenantUserView;

// PATCH /api/v1/auth/tenants/{tenant_id}
export interface TenantUpdateRequest {
  contact_name?: string;
  organisation?: string;
  email?: string;
  phone_number?: string;
}
export type TenantUpdateResponse = TenantView;

// PATCH /api/v1/auth/tenants/{tenant_id}/users/{user_id}
export interface TenantUserUpdateRequest {
  email?: string;
  full_name?: string;
  phone_number?: string;
  username?: string;
  role?: TenantAssignableRole;
}
export type TenantUserUpdateResponse = TenantUserView;
