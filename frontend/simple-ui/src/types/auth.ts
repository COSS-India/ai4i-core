/**
 * Authentication types
 */

export interface User {
  id: number;
  email: string;
  username: string;
  full_name?: string;
  phone_number?: string;
  timezone: string;
  language: string;
  is_active: boolean;
  is_verified: boolean;
  is_superuser: boolean;
  created_at: string;
  updated_at?: string;
  last_login?: string;
  avatar_url?: string;
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

export interface RegisterRequest {
  email: string;
  username: string;
  password: string;
  confirm_password: string;
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
  user_id?: number;
  username?: string;
  permissions: string[];
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
  expires_days?: number;
}

export interface APIKeyResponse {
  id: number;
  key_name: string;
  key_value?: string; // Only returned on creation
  permissions: string[];
  is_active: boolean;
  created_at: string;
  expires_at?: string;
  last_used?: string;
}

export interface OAuth2Provider {
  provider: string;
  client_id: string;
  authorization_url: string;
  scope: string[];
}

export interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
}
