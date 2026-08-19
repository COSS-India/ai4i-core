// Profile-specific types

export const TIMEZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Asia/Kolkata",
  "Asia/Tokyo",
  "Asia/Shanghai",
  "Australia/Sydney",
];

export const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "hi", label: "Hindi" },
  { value: "ta", label: "Tamil" },
  { value: "te", label: "Telugu" },
  { value: "kn", label: "Kannada" },
  { value: "ml", label: "Malayalam" },
  { value: "bn", label: "Bengali" },
  { value: "gu", label: "Gujarati" },
  { value: "mr", label: "Marathi" },
  { value: "pa", label: "Punjabi" },
];

export type {
  TenantAssignableRole,
  TenantView,
  TenantUserView,
  ListTenantsResponse,
  ListUsersResponse,
} from "../../types/tenant";

import type { TenantAssignableRole } from "../../types/tenant";
import type { DefaultOrgUserRole } from "../../utils/defaultTenant";
import { INSTITUTION } from "../../config/constants";

/** Role value in tenant-user create/edit forms (regular or default-org). */
export type TenantUserFormRole =
  | TenantAssignableRole
  | DefaultOrgUserRole
  | "ADMIN"
  | "USAGE VIEWER"
  /** No longer assignable; retained so existing guests survive a profile-only edit. */
  | "GUEST";

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
  role: TenantUserFormRole;
}

/** Assignable tenant-user roles (create/edit forms for regular tenants). */
export const TENANT_USER_ROLE_OPTIONS = [
  { value: "USER", label: "User" },
  { value: "TENANT ADMIN", label: `${INSTITUTION} Admin` },
] as const satisfies ReadonlyArray<{ value: TenantAssignableRole; label: string }>;

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
  role: TenantUserFormRole;
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
  roles?: string[];
}

export type StatusUpdateTargetUnion = StatusUpdateTarget | StatusUpdateUserTarget;

export interface DeleteUserTarget {
  tenant_id: string;
  user_id: string;
  username?: string;
}
