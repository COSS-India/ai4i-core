// Profile-specific types (re-export multi-tenant and extend as needed)

/** Common timezones for user profile */
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

/** Common languages for user profile */
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
  TenantView,
  TenantUserView,
  ListTenantsResponse,
  ListUsersResponse,
} from "../../types/multiTenant";

export type TenantSubView = "adopter" | "tenant";

export interface TenantFormState {
  organization_name: string;
  domain: string;
  contact_name: string;
  contact_email: string;
  contact_phone: string;
  description: string;
  requested_subscriptions: string[];
}

export interface TenantUserFormState {
  tenant_id: string;
  email: string;
  username: string;
  full_name: string;
  services: string[];
  is_approved: boolean;
  role: string;
}

/** Role options for Add User and Filter by Role (match backend role names) */
export const TENANT_USER_ROLE_OPTIONS = [
  { value: "USER", label: "User" },
  { value: "ADMIN", label: "Admin" },
  { value: "GUEST", label: "Guest" },
] as const;

export interface EditTenantFormState {
  tenant_id: string;
  organization_name?: string;
  contact_email?: string;
  domain?: string;
  requested_quotas?: { characters_length?: number; audio_length_in_min?: number };
  usage_quota?: { characters_length?: number; audio_length_in_min?: number };
}

export interface EditUserFormState {
  tenant_id: string;
  user_id: number;
  username?: string;
  email?: string;
  is_approved?: boolean;
  role?: string;
}

export interface StatusUpdateTarget {
  type: "tenant";
  tenant_id: string;
  currentStatus: string;
}

export interface StatusUpdateUserTarget {
  type: "user";
  tenant_id: string;
  user_id: number;
  currentStatus: string;
}

export type StatusUpdateTargetUnion = StatusUpdateTarget | StatusUpdateUserTarget;

export interface DeleteUserTarget {
  tenant_id: string;
  user_id: number;
  username?: string;
}
