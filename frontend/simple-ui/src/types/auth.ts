/**
 * Authentication types
 */

export interface User {
  user_id: string;
  email: string;
  username: string;
  full_name?: string | null;
  phone_number?: string | null;
  timezone?: string;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
  last_login?: string;
  avatar_url?: string;
  preferences?: Record<string, any>;
  roles?: string[];
  tenant_id?: string | null;
  is_tenant_active?: boolean | null;
}

export interface UserUpdateRequest {
  full_name?: string;
  phone_number?: string;
  timezone?: string;
  preferences?: Record<string, any>;
}

export interface LoginRequest {
  email: string;
  password: string;
  remember_me?: boolean;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user?: User; // Optional since API might not include it
}

/** POST /auth/change-password — keeps `message` for backward compatibility
 * with any pre-existing consumer of this endpoint, alongside a fresh token
 * pair for the caller's own session. */
export interface ChangePasswordResponse {
  message: string;
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface RegisterRequest {
  email: string;
  password: string;
  confirm_password: string;
  full_name?: string;
  phone_number?: string;
  timezone?: string;
}

export interface TokenRefreshRequest {
  refresh_token: string;
}

export interface TokenRefreshResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface TokenValidationResponse {
  valid: boolean;
  user_id?: string;
  username?: string;
  tenant_id?: string;
  permission_ids: number[];
  permissions: string[];
  roles: string[];
  token_type?: string;
}

export interface PasswordChangeRequest {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

export interface PasswordResetRequest {
  email: string;
}

export interface PasswordResetConfirm {
  token: string;
  new_password: string;
  confirm_password: string;
}

export interface SetPasswordRequest {
  token: string;
  new_password: string;
  confirm_password: string;
}

export interface SetPasswordStatusResponse {
  valid: boolean;
  status: "valid" | "expired" | "invalid" | "used";
  message: string;
}

export interface VerifyEmailRequest {
  token: string;
}

export interface ResendVerificationRequest {
  email: string;
}

export interface LogoutRequest {
  refresh_token?: string;
}

export interface LogoutResponse {
  message: string;
  logged_out: boolean;
}

export interface APIKeyCreate {
  key_name: string;
  permissions: string[];
  application_id: string;
  expires_days?: number;
  allocated_percentage?: number;
}

export interface APIKeyResponse {
  id: number;
  key_id?: number;  // Alias for id, returned by create endpoint
  key_name: string;
  /** Full raw key only on creation; list/get endpoints return it masked (e.g. "ab12******gh78"). */
  api_key?: string;
  permissions: string[];
  is_active?: boolean;
  is_revoked?: boolean;
  created_at?: string;
  expires_at?: string;
  last_used?: string;
  application_id?: string;
  application_name?: string;
  allocated_percentage?: number | null;
  allocated_budget?: number | null;
  created_by?: string;
}

export interface AdminAPIKeyWithUserResponse extends APIKeyResponse {
  user_id: string;
  user_email: string;
  username: string;
}

/**
 * Form state for the admin “update API key” modal only — not sent to the API.
 * Multi-select uses permission names, sent to the API as-is.
 */
export interface APIKeyUpdate {
  key_name?: string;
  permissions?: string[];
}

/** Response from GET /api/v1/auth/api-keys — grouped by application_id. */
export interface ApiKeyApplicationGroupResponse {
  application_id: string;
  api_keys: APIKeyResponse[];
}

export interface APIKeyListResponse {
  api_keys: APIKeyResponse[];
}

export interface OAuth2Provider {
  provider: string;
  client_id: string;
  authorization_url: string;
  scope: string[];
}

export interface Permission {
  name: string;
  label: string;
}

export interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  // Separate loading states so "Sign in" and "Sign in as Guest" buttons
  // can show their spinners independently.
  isLoginLoading: boolean;
  isGuestLoginLoading: boolean;
  error: string | null;
}
