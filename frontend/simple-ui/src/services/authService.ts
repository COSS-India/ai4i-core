/**
 * Authentication service
 */
import {
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  User,
  TokenRefreshResponse,
  TokenValidationResponse,
  PasswordChangeRequest,
  PasswordResetRequest,
  PasswordResetConfirm,
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
import { apiEndpoints } from './apiEndpoints';
import baseApiService from './baseApiService';
import {
  getStoredAccessToken,
  getStoredRefreshToken,
  setStoredAccessToken,
  setStoredRefreshToken,
  clearTokenStorage,
  getRememberMePreference,
} from '../utils/tokenStorage';
import { responseIndicatesTenantSuspendedOrInactive } from '../utils/tenantInactiveApiErrors';

const authPaths = apiEndpoints.auth.paths;

class AuthService {
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${apiEndpoints.auth.base}${endpoint}`;
    const method = (options.method || 'GET') as
      | 'GET'
      | 'POST'
      | 'PUT'
      | 'PATCH'
      | 'DELETE';
    const requestData =
      typeof options.body === 'string' ? JSON.parse(options.body) : options.body;
    const token = this.getAccessToken();

    try {
      return await baseApiService.request<T>(url, {
        method,
        data: requestData,
        timeout: 10000,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(options.headers as Record<string, string>),
        },
      });
    } catch (error: any) {
      const status = error?.status;
      const errorData: any = error?.responseData ?? {};
      if (
        typeof window !== 'undefined' &&
        responseIndicatesTenantSuspendedOrInactive(status ?? 0, errorData)
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

      // Check if error is "Invalid authentication credentials" (session expiry)
      const errorMessageLower = (error?.message || '').toLowerCase();
      const isInvalidAuth =
        errorMessageLower.includes('invalid authentication credentials') ||
        (status === 401 && errorMessageLower.includes('invalid'));

      if (isInvalidAuth && typeof window !== 'undefined') {
        // Clear tokens and redirect to login
        this.clearAuthTokens();
        this.clearStoredUser();
        window.location.href = '/';
        throw new Error('Session expired. Please sign in again.');
      }

      if (error?.message?.toLowerCase?.().includes('timeout')) {
        console.error('Auth service request timed out:', url);
        throw new Error('Request timeout: Auth service is not responding');
      }

      console.error('Auth service request failed:', error);
      throw error;
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
    return this.requestWithoutAuth<{ id: number; email: string; username: string; message: string }>(
      authPaths.register,
      {
      method: 'POST',
      body: JSON.stringify(data),
      }
    );
  }

  async login(data: LoginRequest): Promise<LoginResponse> {
    // Login endpoint doesn't require authentication
    const response = await this.requestWithoutAuth<LoginResponse>(authPaths.login, {
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
    const response = await this.requestWithoutAuth<LoginResponse>(authPaths.guestLogin, {
      method: 'POST',
    });

    // Guest sessions should stay in session storage by default.
    this.setAccessToken(response.access_token, false);
    this.setRefreshToken(response.refresh_token, false);

    return response;
  }

  async getGuestEnabledServices(): Promise<any> {
    return this.request<any>(authPaths.guestServices);
  }

  // Request method without authentication header (for login/register)
  private async requestWithoutAuth<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${apiEndpoints.auth.base}${endpoint}`;
    const method = (options.method || 'GET') as
      | 'GET'
      | 'POST'
      | 'PUT'
      | 'PATCH'
      | 'DELETE';
    const requestData =
      typeof options.body === 'string' ? JSON.parse(options.body) : options.body;

    try {
      return await baseApiService.request<T>(url, {
        method,
        data: requestData,
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers as Record<string, string>),
        },
      });
    } catch (error) {
      console.error('Auth service request failed:', error);
      throw error;
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
      const response = await this.request<LogoutResponse>(authPaths.logout, {
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
        const response = await this.requestWithoutAuth<TokenRefreshResponse>(authPaths.refresh, {
          method: 'POST',
          body: JSON.stringify({ refresh_token: refreshToken }),
        });

        const rememberMe = getRememberMePreference();
        this.setAccessToken(response.access_token, rememberMe);

        return response;
      } finally {
        this.refreshPromise = null;
      }
    })();

    return this.refreshPromise;
  }

  async validateToken(): Promise<TokenValidationResponse> {
    return this.request<TokenValidationResponse>(authPaths.validate);
  }

  async getCurrentUser(): Promise<User> {
    // Use a longer timeout for /me endpoint as it's critical for auth validation
    return this.requestWithTimeout<User>(authPaths.me, {}, 20000);
  }

  // Request method with custom timeout
  private async requestWithTimeout<T>(
    endpoint: string,
    options: RequestInit = {},
    timeoutMs: number = 10000
  ): Promise<T> {
    const url = `${apiEndpoints.auth.base}${endpoint}`;
    const method = (options.method || 'GET') as
      | 'GET'
      | 'POST'
      | 'PUT'
      | 'PATCH'
      | 'DELETE';
    const requestData =
      typeof options.body === 'string' ? JSON.parse(options.body) : options.body;
    const token = this.getAccessToken();

    return baseApiService.request<T>(url, {
      method,
      data: requestData,
      timeout: timeoutMs,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers as Record<string, string>),
      },
    });
  }

  async updateCurrentUser(data: Partial<User>): Promise<User> {
    return this.request<User>(authPaths.me, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async changePassword(data: PasswordChangeRequest): Promise<{ message: string }> {
    return this.request<{ message: string }>(authPaths.changePassword, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async requestPasswordReset(data: PasswordResetRequest): Promise<{ message: string }> {
    return this.request<{ message: string }>(authPaths.requestPasswordReset, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async resetPassword(data: PasswordResetConfirm): Promise<{ message: string; sign_out_other_sessions?: boolean }> {
    // Public endpoint — token in body authenticates the request. Single-use,
    // 30-minute expiry. Other sessions are revoked server-side.
    return this.requestWithoutAuth<{ message: string; sign_out_other_sessions?: boolean }>('/reset-password', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // ── Email-activation set-password (one-time setup token) ──

  async getSetPasswordStatus(token: string): Promise<SetPasswordStatusResponse> {
    // Bypasses the requestWithoutAuth helper on purpose: this endpoint does NOT
    // return the v2 {success, data} envelope (route uses response_model=
    // SetPasswordStatusResponse), so the helper's auto-unwrap would mangle it.
    const url = `${apiEndpoints.auth.base}${authPaths.setPasswordStatus}?token=${encodeURIComponent(token)}`;
    const res = await fetch(url, { method: 'GET' });
    if (!res.ok) {
      // Backend always returns 200 for valid/expired/used; HTTP error == network/CORS.
      return { valid: false, status: 'invalid', message: `HTTP ${res.status}` };
    }
    return res.json();
  }

  async setPasswordWithToken(data: SetPasswordRequest): Promise<{ message: string }> {
    return this.requestWithoutAuth<{ message: string }>('/set-password', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // ── Email verification (one-time token from /auth/register's verify email) ──

  async verifyEmail(data: VerifyEmailRequest): Promise<{ message: string }> {
    return this.requestWithoutAuth<{ message: string }>('/verify-email', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async resendVerification(data: ResendVerificationRequest): Promise<{ message: string }> {
    return this.requestWithoutAuth<{ message: string }>('/resend-verification', {

      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // API Key management
  async createApiKey(data: APIKeyCreate): Promise<APIKeyResponse> {
    return this.request<APIKeyResponse>(authPaths.apiKeys, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async createApiKeyForUser(data: APIKeyCreate & { user_id: number }): Promise<APIKeyResponse> {
    // Convert user_id to userId (camelCase) for the API payload
    const payload = {
      key_name: data.key_name,
      permissions: data.permissions,
      expires_days: data.expires_days,
      userId: data.user_id, // Send as userId (camelCase) in JSON payload
    };
    return this.request<APIKeyResponse>(authPaths.apiKeys, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async listApiKeys(): Promise<APIKeyListResponse> {
    const data = await this.request<APIKeyListResponse | APIKeyResponse[]>(authPaths.apiKeys);
    // Backend may return { api_keys, selected_api_key_id } or a plain array (legacy)
    if (Array.isArray(data)) {
      return { api_keys: data, selected_api_key_id: null };
    }
    const normalized = data as APIKeyListResponse;
    return {
      api_keys: Array.isArray(normalized.api_keys) ? normalized.api_keys : [],
      selected_api_key_id: normalized.selected_api_key_id ?? null,
    };
  }

  async listAllApiKeys(): Promise<AdminAPIKeyWithUserResponse[]> {
    return this.request<AdminAPIKeyWithUserResponse[]>(authPaths.apiKeysAll);
  }

  async revokeApiKey(keyId: number): Promise<{ message: string }> {
    return this.request<{ message: string }>(`${authPaths.apiKeys}/${keyId}`, {
      method: 'DELETE',
    });
  }

  async updateApiKey(keyId: number, updateData: APIKeyUpdate): Promise<APIKeyResponse> {
    return this.request<APIKeyResponse>(`${authPaths.apiKeys}/${keyId}`, {
      method: 'PATCH',
      body: JSON.stringify(updateData),
    });
  }

  // OAuth2
  async getOAuth2Providers(): Promise<OAuth2Provider[]> {
    return this.request<OAuth2Provider[]>(authPaths.oauth2Providers);
  }

  async exchangeOAuthCode(code: string): Promise<LoginResponse> {
    return this.requestWithoutAuth<LoginResponse>(authPaths.oauth2Exchange, {
      method: 'POST',
      body: JSON.stringify({ code }),
    });
  }

  // User management (Admin / Mod / Tenant Admin)
  async getAllUsers(): Promise<User[]> {
    return this.request<User[]>(`${authPaths.users}?limit=500&offset=0`);
  }

  /** Paginated user list (same endpoint as getAllUsers; for infinite-scroll pickers). */
  async listUsersPage(offset: number, limit: number = 100): Promise<User[]> {
    return this.request<User[]>(`${authPaths.users}?limit=${limit}&offset=${offset}`);
  }

  async getUserById(userId: number): Promise<User> {
    return this.request<User>(`${authPaths.users}/${userId}`);
  }

  // Permissions management (inference-only)
  async getAllPermissions(): Promise<Permission[]> {
    return this.request<Permission[]>(authPaths.inferencePermissions);
  }

  // Utility methods
  isAuthenticated(): boolean {
    return !!this.getAccessToken();
  }

  getStoredUser(): User | null {
    if (typeof window === 'undefined') return null;
    const userStr = sessionStorage.getItem('user') || localStorage.getItem('user');
    if (userStr && !sessionStorage.getItem('user')) {
      // Backward compatibility: migrate legacy localStorage user to sessionStorage.
      sessionStorage.setItem('user', userStr);
      localStorage.removeItem('user');
    }
    return userStr ? JSON.parse(userStr) : null;
  }

  setStoredUser(user: User): void {
    if (typeof window === 'undefined') return;
    // Clear from both storages first
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
    // Clear from both storages first
    localStorage.removeItem('login_timestamp');
    sessionStorage.removeItem('login_timestamp');
    sessionStorage.setItem('login_timestamp', timestamp);
  }

  /**
   * Get the login timestamp
   */
  public getLoginTimestamp(): number | null {
    if (typeof window === 'undefined') return null;
    const timestampStr = sessionStorage.getItem('login_timestamp') || localStorage.getItem('login_timestamp');
    if (timestampStr && !sessionStorage.getItem('login_timestamp')) {
      // Backward compatibility: migrate legacy localStorage timestamp to sessionStorage.
      sessionStorage.setItem('login_timestamp', timestampStr);
      localStorage.removeItem('login_timestamp');
    }
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
    const rememberMe = getRememberMePreference();
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
    const rememberMe = getRememberMePreference();
    const sessionDurationMs = rememberMe 
      ? 7 * 24 * 60 * 60 * 1000  // 7 days
      : 24 * 60 * 60 * 1000;      // 24 hours
    const timeRemaining = sessionDurationMs - (now - loginTimestamp);
    return timeRemaining > 0 ? timeRemaining : 0;
  }
}

export const authService = new AuthService();
export default authService;
