// Multi-tenant admin API types (match backend TenantViewResponse, TenantUserViewResponse)

export interface TenantView {
  id: string;
  tenant_id: string;
  user_id: number;
  organization_name: string;
  email: string;
  domain: string;
  schema?: string;
  subscriptions: string[];
  status: string;
  quotas?: Record<string, unknown>;
  usage_quota?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ListTenantsResponse {
  count: number;
  tenants: TenantView[];
}

export interface TenantUserView {
  id: string;
  user_id: number;
  tenant_id: string;
  username: string;
  email: string;
  role?: string;
  subscriptions: string[];
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ListUsersResponse {
  count: number;
  users: TenantUserView[];
}

// Register tenant (POST /admin/register/tenant)
export interface TenantRegisterRequest {
  organization_name: string;
  domain: string;
  contact_email: string;
  requested_subscriptions?: string[];
}

export interface TenantRegisterResponse {
  id: string;
  tenant_id: string;
  schema_name: string;
  subscriptions: string[];
  quotas: Record<string, unknown>;
  usage_quota?: Record<string, unknown>;
  status: string;
  token: string;
  message?: string;
}

// Register user (POST /admin/register/users)
export interface UserRegisterRequest {
  tenant_id: string;
  email: string;
  username: string;
  full_name?: string;
  services: string[];
  is_approved?: boolean;
  role?: string;
}

export interface UserRegisterResponse {
  user_id: number;
  tenant_id: string;
  username: string;
  email: string;
  services: string[];
  schema: string;
  created_at: string;
}

// View tenant (GET /admin/view/tenant?tenant_id=)
// Response is same shape as TenantView with extra detail fields

// View user (GET /admin/view/user?user_id=)
// Response is same shape as TenantUserView with extra detail fields

// PATCH /admin/update/tenants/status
export interface TenantStatusUpdateRequest {
  tenant_id: string;
  status: 'ACTIVE' | 'SUSPENDED' | 'DEACTIVATED';
  reason?: string;
  suspended_until?: string;
}

export interface TenantStatusUpdateResponse {
  tenant_id: string;
  old_status: string;
  new_status: string;
}

// PATCH /admin/update/users/status
export interface TenantUserStatusUpdateRequest {
  tenant_id: string;
  user_id: number;
  status: 'ACTIVE' | 'PENDING' | 'SUSPENDED' | 'DEACTIVATED';
}

export interface TenantUserStatusUpdateResponse {
  tenant_id: string;
  user_id: number;
  old_status: string;
  new_status: string;
}

// PATCH /admin/update/tenant (partial update)
export interface TenantUpdateRequest {
  tenant_id: string;
  organization_name?: string;
  contact_email?: string;
  domain?: string;
  requested_quotas?: { characters_length?: number; audio_length_in_min?: number };
  usage_quota?: { characters_length?: number; audio_length_in_min?: number };
}

export interface TenantUpdateResponse {
  tenant_id: string;
  message: string;
  changes: Record<string, unknown>;
  updated_fields: string[];
}

// PATCH /admin/update/user (partial update: username, email, is_approved, role)
export interface TenantUserUpdateRequest {
  tenant_id: string;
  user_id: number;
  username?: string;
  email?: string;
  is_approved?: boolean;
  role?: string;
}

export interface TenantUserUpdateResponse {
  tenant_id: string;
  user_id: number;
  message: string;
  changes: Record<string, { old: unknown; new: unknown }>;
  updated_fields: string[];
}

// DELETE /admin/delete/user
export interface TenantUserDeleteRequest {
  tenant_id: string;
  user_id: number;
}

export interface TenantUserDeleteResponse {
  tenant_id: string;
  user_id: number;
  message: string;
}

// GET /list/services – list all registered (active) services
export interface ServiceView {
  id: number;
  service_name: string;
  unit_type?: string;
  price_per_unit?: number;
  currency?: string;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface ListServicesResponse {
  count: number;
  services: ServiceView[];
}

// POST /tenant/subscriptions/add – add subscriptions to a tenant
export interface TenantSubscriptionAddRequest {
  tenant_id: string;
  subscriptions: string[];
}

// POST /tenant/subscriptions/remove – remove subscriptions from a tenant
export interface TenantSubscriptionRemoveRequest {
  tenant_id: string;
  subscriptions: string[];
}

export interface TenantSubscriptionResponse {
  tenant_id: string;
  subscriptions: string[];
}

// POST /user/subscriptions/add – add subscriptions to a tenant user
export interface UserSubscriptionAddRequest {
  tenant_id: string;
  user_id: number;
  subscriptions: string[];
}

// POST /user/subscriptions/remove – remove subscriptions from a tenant user
export interface UserSubscriptionRemoveRequest {
  tenant_id: string;
  user_id: number;
  subscriptions: string[];
}

export interface UserSubscriptionResponse {
  tenant_id: string;
  user_id: number;
  subscriptions: string[];
}
