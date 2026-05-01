/**
 * Authentication service
 */
import {
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  User,
  TokenRefreshRequest,
  TokenRefreshResponse,
  TokenValidationResponse,
  PasswordChangeRequest,
  PasswordResetRequest,
  PasswordResetConfirm,
  SetPasswordRequest,
  SetPasswordStatusResponse,
  VerifyEmailRequest,
  ResendVerificationRequest,
  LogoutRequest,
  LogoutResponse,
  APIKeyCreate,
  APIKeyResponse,
  APIKeyListResponse,
  AdminAPIKeyWithUserResponse,
  APIKeyUpdate,
  OAuth2Provider,
  Permission,
} from '../types/auth';
import { API_BASE_URL, apiService } from './api';
import { apiEndpoints } from './apiEndpoints';
import {
  getStoredAccessToken,
  getStoredRefreshToken,
  getRememberMeFromStorage,
  setStoredAccessToken,
  setStoredRefreshToken,
  clearTokenStorage,
} from '../utils/tokenStorage';
import { responseIndicatesTenantSuspendedOrInactive } from '../utils/tenantInactiveApiErrors';

const authPath = apiEndpoints.auth.paths;

class AuthService {
  private baseUrl: string;

  constructor() {
    this.baseUrl = `${API_BASE_URL}${apiEndpoints.auth.base}`;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    const defaultHeaders: HeadersInit = {
      'Content-Type': 'application/json',
    };

    // Add authorization header if token exists
    const token = this.getAccessToken();
    if (token) {
      defaultHeaders.Authorization = `Bearer ${token}`;
    }

    const config: RequestInit = {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
    };

    // Add timeout to prevent hanging (10 seconds)
    const timeoutMs = 10000;

    try {
      const response = await apiService.request(
        (config.method || 'GET') as any,
        url,
        config.body,
        {
          headers: config.headers as Record<string, string>,
          timeout: timeoutMs,
        }
      );
      const json = response.data;
      // Unwrap v2 response envelope: { success: true, data: {...} }
      if (json && typeof json === 'object' && 'success' in json && 'data' in json) {
        return json.data as T;
      }
      return json as T;
    } catch (error: any) {
      if (error?.code === 'ECONNABORTED') {
        console.error('Auth service request timed out:', url);
        throw new Error('Request timeout: Auth service is not responding');
      }

      const status = error?.response?.status;
      const errorData = error?.response?.data ?? {};
      if (
        typeof window !== 'undefined' &&
        typeof status === 'number' &&
        responseIndicatesTenantSuspendedOrInactive(status, errorData)
      ) {
        try {
          const { forceFrontendSessionEnd } = await import('../hooks/useAuth');
          forceFrontendSessionEnd();
        } catch {
          this.clearAuthTokens();
          this.clearStoredUser();
          window.location.assign('/auth');
        }
        throw new Error('Your organization account is no longer active. Please sign in again.');
      }

      let errorMessage = status ? `HTTP error! status: ${status}` : 'Request failed';
      if (errorData?.detail) {
        const d = errorData.detail;
        if (typeof d === 'string') {
          errorMessage = d;
        } else if (typeof d === 'object' && d !== null && typeof (d as any).message === 'string') {
          errorMessage = (d as any).message;
        } else if (typeof d === 'object' && d !== null) {
          errorMessage = (d as any).message != null ? String((d as any).message) : JSON.stringify(d);
        } else {
          errorMessage = String(d);
        }
      } else if (errorData?.message) {
        errorMessage = String(errorData.message);
      } else if (typeof errorData === 'string') {
        errorMessage = errorData;
      } else if (Array.isArray(errorData) && errorData.length > 0) {
        errorMessage = errorData.map((err: any) => err.detail?.message ?? err.detail ?? err.message ?? String(err)).join(', ');
      }

      const errorMessageLower = errorMessage.toLowerCase();
      const isInvalidAuth = errorMessageLower.includes('invalid authentication credentials') ||
        (status === 401 && errorMessageLower.includes('invalid'));

      if (isInvalidAuth && typeof window !== 'undefined') {
        this.clearAuthTokens();
        this.clearStoredUser();
        window.location.href = '/';
        throw new Error('Session expired. Please sign in again.');
      }

      console.error('Auth service request failed:', error);
      const normalizedError = new Error(errorMessage);
      (normalizedError as any).status = status ?? (error as any)?.status;
      throw normalizedError;
    }
  }

  // Token management with remember me support (encrypted at rest via tokenStorage)
  public getAccessToken(): string | null {
    return getStoredAccessToken();
  }

  public setAccessToken(token: string, rememberMe: boolean = true): void {
    if (typeof window === 'undefined') return;
    setStoredAccessToken(token, rememberMe);
    this.setLoginTimestamp();
  }

  public getRefreshToken(): string | null {
    return getStoredRefreshToken();
  }

  public setRefreshToken(token: string, rememberMe: boolean = true): void {
    if (typeof window === 'undefined') return;
    setStoredRefreshToken(token, rememberMe);
  }

  private clearTokens(): void {
    clearTokenStorage();
  }

  public clearAuthTokens(): void {
    this.clearTokens();
  }

  // Authentication methods
  async register(data: RegisterRequest): Promise<{ id: number; email: string; username: string; message: string }> {
    // Register endpoint doesn't require authentication
    return this.requestWithoutAuth<{ id: number; email: string; username: string; message: string }>(authPath.register, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async login(data: LoginRequest): Promise<LoginResponse> {
    // Login endpoint doesn't require authentication
    const response = await this.requestWithoutAuth<LoginResponse>(authPath.login, {
      method: 'POST',
      body: JSON.stringify(data),
    });

    // Store tokens with remember_me preference
    const rememberMe = data.remember_me ?? true; // Default to true for backward compatibility
    this.setAccessToken(response.access_token, rememberMe);
    this.setRefreshToken(response.refresh_token, rememberMe);

    return response;
  }

  async guestLogin(): Promise<LoginResponse> {
    const response = await this.requestWithoutAuth<LoginResponse>(authPath.guestLogin, {
      method: 'POST',
    });

    // Guest sessions should stay in session storage by default.
    this.setAccessToken(response.access_token, false);
    this.setRefreshToken(response.refresh_token, false);

    return response;
  }

  async getGuestEnabledServices(): Promise<any> {
    return this.request<any>(authPath.rolesListGuestServices);
  }

  // Request method without authentication header (for login/register)
  private async requestWithoutAuth<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    const defaultHeaders: HeadersInit = {
      'Content-Type': 'application/json',
    };

    const config: RequestInit = {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
    };

    try {
      const response = await apiService.request(
        (config.method || 'GET') as any,
        url,
        config.body,
        { headers: config.headers as Record<string, string> }
      );
      const json = response.data;
      // Unwrap v2 response envelope: { success: true, data: {...} }
      if (json && typeof json === 'object' && 'success' in json && 'data' in json) {
        return json.data as T;
      }
      return json as T;
    } catch (error: any) {
      const status = error?.response?.status;
      const errorData = error?.response?.data ?? {};
      let errorMessage = status ? `HTTP error! status: ${status}` : 'Request failed';
      if (typeof errorData === 'string') {
        errorMessage = errorData;
      } else if (errorData?.detail) {
        const d = errorData.detail;
        if (typeof d === 'string') {
          errorMessage = d;
        } else if (typeof d === 'object' && d !== null && typeof d.message === 'string') {
          errorMessage = d.message;
        } else if (typeof d === 'object' && d !== null) {
          errorMessage = (d as any).message != null ? String((d as any).message) : JSON.stringify(d);
        } else {
          errorMessage = String(d);
        }
      } else if (errorData?.message) {
        errorMessage = String(errorData.message);
      } else if (Array.isArray(errorData)) {
        errorMessage = errorData.map((err: any) =>
          err.detail?.message ?? err.detail ?? err.message ?? String(err)
        ).join(', ');
      } else if (typeof errorData === 'object' && Object.keys(errorData).length > 0) {
        const d = errorData.detail ?? errorData.message ?? errorData.error;
        errorMessage = typeof d === 'object' && d !== null && (d as any).message != null
          ? String((d as any).message)
          : d != null ? String(d) : JSON.stringify(errorData);
      }

      console.error('Auth service request failed:', error);
      const normalizedError = new Error(errorMessage);
      (normalizedError as any).status = status ?? (error as any)?.status;
      throw normalizedError;
    }
  }

  async logout(data: LogoutRequest = {}): Promise<LogoutResponse> {
    // Get refresh token from storage (received during login)
    const refreshToken = this.getRefreshToken();

    // Always clear local state, even if API call fails
    const clearLocalState = () => {
      this.clearTokens();
      this.clearStoredUser();
    };

    if (!refreshToken) {
      // No refresh token, just clear local state
      clearLocalState();
      throw new Error('No refresh token found');
    }

    try {
      const response = await this.request<LogoutResponse>(authPath.logout, {
        method: 'POST',
        body: JSON.stringify({
          refresh_token: data.refresh_token || refreshToken,
        }),
      });

      // Clear tokens after successful logout
      clearLocalState();

      return response;
    } catch (error) {
      // Even if logout API fails, clear local state
      console.error('Logout API call failed, but clearing local state:', error);
      clearLocalState();
      throw error;
    }
  }

  // Single-flight: only one POST /auth/refresh at a time; concurrent callers wait for the same result.
  private refreshPromise: Promise<TokenRefreshResponse> | null = null;

  async refreshToken(): Promise<TokenRefreshResponse> {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) {
      throw new Error('No refresh token available');
    }

    if (this.refreshPromise !== null) {
      return this.refreshPromise;
    }

    this.refreshPromise = (async () => {
      try {
        const response = await this.requestWithoutAuth<TokenRefreshResponse>(authPath.refresh, {
          method: 'POST',
          body: JSON.stringify({ refresh_token: refreshToken }),
        });

        const rememberMe = getRememberMeFromStorage();
        this.setAccessToken(response.access_token, rememberMe);

        return response;
      } finally {
        this.refreshPromise = null;
      }
    })();

    return this.refreshPromise;
  }

  async validateToken(): Promise<TokenValidationResponse> {
    return this.request<TokenValidationResponse>(authPath.validate);
  }

  async getCurrentUser(): Promise<User> {
    // Use a longer timeout for /me endpoint as it's critical for auth validation
    return this.requestWithTimeout<User>(authPath.me, {}, 20000);
  }

  // Request method with custom timeout
  private async requestWithTimeout<T>(
    endpoint: string,
    options: RequestInit = {},
    timeoutMs: number = 10000
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    const defaultHeaders: HeadersInit = {
      'Content-Type': 'application/json',
    };

    // Add authorization header if token exists
    const token = this.getAccessToken();
    if (token) {
      defaultHeaders.Authorization = `Bearer ${token}`;
    }

    const config: RequestInit = {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
    };

    try {
      const response = await apiService.request(
        (config.method || 'GET') as any,
        url,
        config.body,
        {
          headers: config.headers as Record<string, string>,
          timeout: timeoutMs,
        }
      );
      const json = response.data;
      // Unwrap v2 response envelope: { success: true, data: {...} }
      if (json && typeof json === 'object' && 'success' in json && 'data' in json) {
        return json.data as T;
      }
      return json as T;
    } catch (error: any) {
      if (error?.code === 'ECONNABORTED') {
        console.error('Auth service request timed out:', url);
        throw new Error(`Request timeout: Auth service is not responding (timeout: ${timeoutMs}ms)`);
      }

      const status = error?.response?.status;
      const errorData = error?.response?.data ?? {};
      let errorMessage = status ? `HTTP error! status: ${status}` : 'Request failed';
      if (errorData?.detail) {
        errorMessage = String(errorData.detail);
      } else if (errorData?.message) {
        errorMessage = String(errorData.message);
      } else if (typeof errorData === 'string') {
        errorMessage = errorData;
      } else if (Array.isArray(errorData) && errorData.length > 0) {
        errorMessage = errorData.map((err: any) => err.detail || err.message || String(err)).join(', ');
      }

      console.error('Auth service request failed:', error);
      const normalizedError = new Error(errorMessage);
      (normalizedError as any).status = status ?? (error as any)?.status;
      throw normalizedError;
    }
  }

  async updateCurrentUser(data: Partial<User>): Promise<User> {
    return this.request<User>(authPath.me, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async changePassword(data: PasswordChangeRequest): Promise<{ message: string }> {
    return this.request<{ message: string }>(authPath.changePassword, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async requestPasswordReset(data: PasswordResetRequest): Promise<{ message: string }> {
    // Public endpoint — no auth header. Always returns 200 with generic message
    // (anti-enumeration). Backend rate-limits to 3 per email per hour; on 429
    // the user sees a "try again later" error.
    return this.requestWithoutAuth<{ message: string }>(authPath.forgotPassword, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async resetPassword(data: PasswordResetConfirm): Promise<{ message: string; sign_out_other_sessions?: boolean }> {
    // Public endpoint — token in body authenticates the request. Single-use,
    // 30-minute expiry. Other sessions are revoked server-side.
    return this.requestWithoutAuth<{ message: string; sign_out_other_sessions?: boolean }>(authPath.resetPassword, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // ── Email-activation set-password (one-time setup token) ──

  async getSetPasswordStatus(token: string): Promise<SetPasswordStatusResponse> {
    // Bypasses the requestWithoutAuth helper on purpose: this endpoint does NOT
    // return the v2 {success, data} envelope (route uses response_model=
    // SetPasswordStatusResponse), so the helper's auto-unwrap would mangle it.
    const url = `${this.baseUrl}${authPath.setPasswordStatus(token)}`;
    try {
      const res = await apiService.request<SetPasswordStatusResponse>('GET', url);
      return res.data;
    } catch (error: any) {
      const status = error?.response?.status;
      return { valid: false, status: 'invalid', message: status ? `HTTP ${status}` : 'Network error' };
    }
  }

  async setPasswordWithToken(data: SetPasswordRequest): Promise<{ message: string }> {
    return this.requestWithoutAuth<{ message: string }>(authPath.setPassword, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // ── Email verification (one-time token from /auth/register's verify email) ──

  async verifyEmail(data: VerifyEmailRequest): Promise<{ message: string }> {
    return this.requestWithoutAuth<{ message: string }>(authPath.verifyEmail, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async resendVerification(data: ResendVerificationRequest): Promise<{ message: string }> {
    return this.requestWithoutAuth<{ message: string }>(authPath.resendVerification, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async resendSetupLink(data: { email: string }): Promise<{ message: string }> {
    return this.requestWithoutAuth<{ message: string }>(authPath.resendSetupLink, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // API Key management
  async createApiKey(data: APIKeyCreate): Promise<APIKeyResponse> {
    return this.request<APIKeyResponse>(authPath.apiKeys, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async createApiKeyForUser(data: APIKeyCreate & { user_id: string }): Promise<APIKeyResponse> {
    const payload = {
      key_name: data.key_name,
      permissions: data.permissions,
      expires_days: data.expires_days,
      user_id: data.user_id,
    };
    return this.request<APIKeyResponse>(authPath.apiKeys, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async listApiKeys(): Promise<APIKeyListResponse> {
    const data = await this.request<APIKeyListResponse | APIKeyResponse[]>(authPath.apiKeys);
    if (Array.isArray(data)) {
      return { api_keys: data };
    }
    return { api_keys: Array.isArray(data?.api_keys) ? data.api_keys : [] };
  }

  async listAllApiKeys(): Promise<AdminAPIKeyWithUserResponse[]> {
    return this.request<AdminAPIKeyWithUserResponse[]>(authPath.apiKeysAll);
  }

  async revokeApiKey(apiKeyValue: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/api-keys/${apiKeyValue}`, {
      method: 'DELETE',
    });
  }

  async updateApiKey(apiKeyValue: string, updateData: APIKeyUpdate): Promise<APIKeyResponse> {
    return this.request<APIKeyResponse>(`/api-keys/${apiKeyValue}`, {
      method: 'PATCH',
      body: JSON.stringify(updateData),
    });
  }

  // OAuth2
  async getOAuth2Providers(): Promise<OAuth2Provider[]> {
    return this.request<OAuth2Provider[]>(authPath.oauth2Providers);
  }

  async exchangeOAuthCode(code: string): Promise<LoginResponse> {
    return this.requestWithoutAuth<LoginResponse>(authPath.oauth2Exchange, {
      method: 'POST',
      body: JSON.stringify({ code }),
    });
  }

  // User management (Admin / Mod / Tenant Admin)
  async getAllUsers(): Promise<User[]> {
    return this.request<User[]>(authPath.usersInitial);
  }

  /** Paginated user list (same endpoint as getAllUsers; for infinite-scroll pickers). */
  async listUsersPage(offset: number, limit: number = 100): Promise<User[]> {
    return this.request<User[]>(authPath.usersPage(offset, limit));
  }

  async getUserById(userId: string): Promise<User> {
    return this.request<User>(authPath.userById(userId));
  }

  // Permissions management (inference-only)
  async getAllPermissions(): Promise<Permission[]> {
    return this.request<Permission[]>(authPath.inferencePermissions);
  }

  // Utility methods
  isAuthenticated(): boolean {
    return !!this.getAccessToken();
  }

  getStoredUser(): User | null {
    if (typeof window === 'undefined') return null;
    const userStr = sessionStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
  }

  setStoredUser(user: User): void {
    if (typeof window === 'undefined') return;
    localStorage.removeItem('user');
    sessionStorage.removeItem('user');
    sessionStorage.setItem('user', JSON.stringify(user));
  }

  clearStoredUser(): void {
    if (typeof window === 'undefined') return;
    localStorage.removeItem('user');
    sessionStorage.removeItem('user');
  }

  // Token expiry checking and proactive refresh
  /**
   * Decode JWT token payload
   */
  private decodeToken(token: string): any | null {
    try {
      // JWT has 3 parts: header.payload.signature
      const parts = token.split('.');
      if (parts.length !== 3) {
        return null;
      }

      // Decode the payload (second part)
      const payload = parts[1];
      const decoded = atob(payload);
      return JSON.parse(decoded);
    } catch (error) {
      console.error('Failed to decode token:', error);
      return null;
    }
  }

  /**
   * Get token expiration time in milliseconds
   */
  public getTokenExpiry(): number | null {
    const token = this.getAccessToken();
    if (!token) {
      return null;
    }

    const payload = this.decodeToken(token);
    if (!payload || !payload.exp) {
      return null;
    }

    // JWT exp is in seconds, convert to milliseconds
    return payload.exp * 1000;
  }

  /**
   * Check if token is expired
   */
  public isTokenExpired(): boolean {
    const expiry = this.getTokenExpiry();
    if (!expiry) {
      return true; // If we can't get expiry, assume expired
    }

    return Date.now() >= expiry;
  }

  /**
   * Check if token is expiring soon (within threshold)
   * @param thresholdMinutes - Minutes before expiry to consider "expiring soon" (default: 5)
   */
  public isTokenExpiringSoon(thresholdMinutes: number = 5): boolean {
    const expiry = this.getTokenExpiry();
    if (!expiry) {
      return true; // If we can't get expiry, assume expiring soon
    }

    const thresholdMs = thresholdMinutes * 60 * 1000;
    const timeUntilExpiry = expiry - Date.now();

    return timeUntilExpiry < thresholdMs;
  }

  /**
   * Get time until token expiry in milliseconds
   */
  public getTimeUntilExpiry(): number | null {
    const expiry = this.getTokenExpiry();
    if (!expiry) {
      return null;
    }

    return expiry - Date.now();
  }

  /**
   * Proactively refresh token if it's expiring soon
   * @param thresholdMinutes - Refresh if token expires within this many minutes (default: 5)
   * @returns true if token is valid (either not expiring or successfully refreshed), false otherwise
   */
  public async refreshIfExpiringSoon(thresholdMinutes: number = 5): Promise<boolean> {
    if (!this.isAuthenticated()) {
      return false;
    }

    // Check if token is expiring soon (no API call)
    if (!this.isTokenExpiringSoon(thresholdMinutes)) {
      return true;
    }

    // Token is expiring soon or expired; refreshToken() is single-flight so many callers = one POST /refresh
    try {
      await this.refreshToken();
      return true;
    } catch (error) {
      console.error('Failed to refresh token:', error);
      return false;
    }
  }

  // Auto-refresh token (legacy method, kept for compatibility)
  async ensureValidToken(): Promise<boolean> {
    if (!this.isAuthenticated()) {
      return false;
    }

    try {
      await this.validateToken();
      return true;
    } catch (error) {
      // Try to refresh token
      try {
        await this.refreshToken();
        return true;
      } catch (refreshError) {
        // Refresh failed, clear tokens
        this.clearTokens();
        this.clearStoredUser();
        return false;
      }
    }
  }

  // Session expiry tracking (7 days if remember_me, else 24 hours)
  /**
   * Store the login timestamp
   */
  private setLoginTimestamp(): void {
    if (typeof window === 'undefined') return;
    const timestamp = Date.now().toString();
    localStorage.removeItem('login_timestamp');
    sessionStorage.removeItem('login_timestamp');
    sessionStorage.setItem('login_timestamp', timestamp);
  }

  /**
   * Get the login timestamp
   */
  public getLoginTimestamp(): number | null {
    if (typeof window === 'undefined') return null;
    const timestampStr = sessionStorage.getItem('login_timestamp');
    return timestampStr ? parseInt(timestampStr, 10) : null;
  }

  /**
   * Check if the session has expired
   * - 7 days if remember_me is true
   * - 24 hours if remember_me is false
   */
  public isSessionExpired(): boolean {
    const loginTimestamp = this.getLoginTimestamp();
    if (!loginTimestamp) {
      // No timestamp found, consider expired
      return true;
    }
    const now = Date.now();
    const rememberMe = getRememberMeFromStorage();
    const sessionDurationMs = rememberMe
      ? 7 * 24 * 60 * 60 * 1000  // 7 days
      : 24 * 60 * 60 * 1000;      // 24 hours
    return (now - loginTimestamp) >= sessionDurationMs;
  }

  /**
   * Get time remaining until session expiry in milliseconds
   * - 7 days if remember_me is true
   * - 24 hours if remember_me is false
   */
  public getTimeUntilSessionExpiry(): number | null {
    const loginTimestamp = this.getLoginTimestamp();
    if (!loginTimestamp) {
      return null;
    }
    const now = Date.now();
    const rememberMe = getRememberMeFromStorage();
    const sessionDurationMs = rememberMe
      ? 7 * 24 * 60 * 60 * 1000  // 7 days
      : 24 * 60 * 60 * 1000;      // 24 hours
    const timeRemaining = sessionDurationMs - (now - loginTimestamp);
    return timeRemaining > 0 ? timeRemaining : 0;
  }
}

export const authService = new AuthService();
export default authService;
