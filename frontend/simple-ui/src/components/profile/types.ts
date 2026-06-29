// Profile-specific types

export type {
  TenantAssignableRole,
  TenantView,
  TenantUserView,
  ListTenantsResponse,
  ListUsersResponse,
} from "../../types/tenant";

import type { TenantAssignableRole } from "../../types/tenant";

export interface TenantFormState {
  organisation: string;
  contact_name: string;
  email: string;
  phone_number: string;
}

export interface TenantUserFormState {
  tenant_id: string;
  email: string;
  full_name: string;
  phone_number: string;
  role: TenantAssignableRole;
}

export interface EditTenantFormState {
  tenant_id: string;
  organisation?: string;
  contact_name?: string;
  email?: string;
  phone_number?: string;
}

export interface EditUserFormState {
  tenant_id: string;
  user_id: string;
  username?: string;
  email?: string;
  full_name?: string;
  phone_number?: string;
  role: TenantAssignableRole;
}

export interface StatusUpdateTarget {
  type: "tenant";
  tenant_id: string;
  currentStatus: string;
}

export interface StatusUpdateUserTarget {
  type: "user";
  tenant_id: string;
  user_id: string;
  currentStatus: string;
  role?: string;
}

export type StatusUpdateTargetUnion = StatusUpdateTarget | StatusUpdateUserTarget;

export interface DeleteUserTarget {
  tenant_id: string;
  user_id: string;
  username?: string;
}
