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
  LogoutRequest,
  LogoutResponse,
  APIKeyCreate,
  APIKeyResponse,
  OAuth2Provider,
  Permission,
} from '../types/auth';
import { API_BASE_URL } from './api';

class AuthService {
  private baseUrl: string;

  constructor() {
    this.baseUrl = `${API_BASE_URL}/api/v1/auth`;
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
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    
    try {
      const response = await fetch(url, {
        ...config,
        signal: controller.signal,
      });
      
      clearTimeout(timeoutId);
      
      if (!response.ok) {
        let errorData: any = {};
        try {
          const text = await response.text();
          if (text) {
            errorData = JSON.parse(text);
          }
        } catch (e) {
          // If JSON parsing fails, use empty object
          errorData = {};
        }
        
        // Extract error message from various possible formats
        let errorMessage = `HTTP error! status: ${response.status}`;
        if (errorData?.detail) {
          errorMessage = String(errorData.detail);
        } else if (errorData?.message) {
          errorMessage = String(errorData.message);
        } else if (typeof errorData === 'string') {
          errorMessage = errorData;
        } else if (Array.isArray(errorData) && errorData.length > 0) {
          errorMessage = errorData.map((err: any) => err.detail || err.message || String(err)).join(', ');
        }
        
        // Add status code to error message for debugging
        const error = new Error(errorMessage);
        (error as any).status = response.status;
        throw error;
      }

      return await response.json();
    } catch (error: any) {
      clearTimeout(timeoutId);
      if (error.name === 'AbortError') {
        console.error('Auth service request timed out:', url);
        throw new Error('Request timeout: Auth service is not responding');
      }
      console.error('Auth service request failed:', error);
      // Preserve the original error message and status if available
      if (error.status) {
        (error as any).status = error.status;
      }
      throw error;
    }
  }

  // Token management with remember me support
  private getStorage(): Storage {
    if (typeof window === 'undefined') return localStorage;
    // Check if remember_me preference is stored
    const rememberMe = localStorage.getItem('remember_me') === 'true';
    return rememberMe ? localStorage : sessionStorage;
  }

  public getAccessToken(): string | null {
    if (typeof window === 'undefined') return null;
    // Check both storages (for backward compatibility and migration)
    return localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
  }

  public setAccessToken(token: string, rememberMe: boolean = true): void {
    if (typeof window === 'undefined') return;
    // Store remember_me preference
    localStorage.setItem('remember_me', rememberMe ? 'true' : 'false');
    // Clear from both storages first
    localStorage.removeItem('access_token');
    sessionStorage.removeItem('access_token');
    // Store in appropriate storage
    if (rememberMe) {
      localStorage.setItem('access_token', token);
    } else {
      sessionStorage.setItem('access_token', token);
    }
    // Store login timestamp for session expiry tracking (24 hours)
    this.setLoginTimestamp();
  }

  public getRefreshToken(): string | null {
    if (typeof window === 'undefined') return null;
    // Check both storages (for backward compatibility and migration)
    return localStorage.getItem('refresh_token') || sessionStorage.getItem('refresh_token');
  }

  public setRefreshToken(token: string, rememberMe: boolean = true): void {
    if (typeof window === 'undefined') return;
    // Store remember_me preference
    localStorage.setItem('remember_me', rememberMe ? 'true' : 'false');
    // Clear from both storages first
    localStorage.removeItem('refresh_token');
    sessionStorage.removeItem('refresh_token');
    // Store in appropriate storage
    if (rememberMe) {
      localStorage.setItem('refresh_token', token);
    } else {
      sessionStorage.setItem('refresh_token', token);
    }
  }

  private clearTokens(): void {
    if (typeof window === 'undefined') return;
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('refresh_token');
    localStorage.removeItem('remember_me');
    localStorage.removeItem('login_timestamp');
    sessionStorage.removeItem('login_timestamp');
  }

  public clearAuthTokens(): void {
    this.clearTokens();
  }

  // Authentication methods
  async register(data: RegisterRequest): Promise<User> {
    // Register endpoint doesn't require authentication
    return this.requestWithoutAuth<User>('/register', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async login(data: LoginRequest): Promise<LoginResponse> {
    // Login endpoint doesn't require authentication
    const response = await this.requestWithoutAuth<LoginResponse>('/login', {
      method: 'POST',
      body: JSON.stringify(data),
    });

    // Store tokens with remember_me preference
    const rememberMe = data.remember_me ?? true; // Default to true for backward compatibility
    this.setAccessToken(response.access_token, rememberMe);
    this.setRefreshToken(response.refresh_token, rememberMe);

    return response;
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
      const response = await fetch(url, config);
      
      if (!response.ok) {
        let errorData: any = {};
        try {
          const text = await response.text();
          if (text) {
            try {
              errorData = JSON.parse(text);
            } catch (e) {
              // If JSON parsing fails, use text as error message
              errorData = { detail: text };
            }
          }
        } catch (textError) {
          console.error('Failed to parse error response:', textError);
          errorData = {};
        }
        
        // Handle different error response formats
        let errorMessage = `HTTP error! status: ${response.status}`;
        if (typeof errorData === 'string') {
          errorMessage = errorData;
        } else if (errorData?.detail) {
          // Extract the detail field which contains the error message
          errorMessage = String(errorData.detail);
        } else if (errorData?.message) {
          errorMessage = String(errorData.message);
        } else if (Array.isArray(errorData)) {
          // Handle array of errors
          errorMessage = errorData.map((err: any) => 
            err.detail || err.message || String(err)
          ).join(', ');
        } else if (typeof errorData === 'object' && Object.keys(errorData).length > 0) {
          // Try to extract meaningful error from object
          const errorText = errorData.detail || errorData.message || errorData.error;
          errorMessage = errorText ? String(errorText) : JSON.stringify(errorData);
        }
        
        // Add status code to error for better debugging
        const error = new Error(errorMessage);
        (error as any).status = response.status;
        throw error;
      }

      return await response.json();
    } catch (error) {
      console.error('Auth service request failed:', error);
      // Re-throw as Error if it's not already one, with proper message
      if (error instanceof Error) {
        throw error;
      } else {
        throw new Error(String(error));
      }
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
      const response = await this.request<LogoutResponse>('/logout', {
        method: 'POST',
        headers: {
          'x-auth-source': 'AUTH_TOKEN',
        },
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

  async refreshToken(): Promise<TokenRefreshResponse> {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) {
      throw new Error('No refresh token available');
    }

    // Use requestWithoutAuth for refresh endpoint - it doesn't need Authorization header
    // The refresh_token in the body is sufficient
    const response = await this.requestWithoutAuth<TokenRefreshResponse>('/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    // Update access token with same remember_me preference
    const rememberMe = localStorage.getItem('remember_me') === 'true';
    this.setAccessToken(response.access_token, rememberMe);

    return response;
  }

  async validateToken(): Promise<TokenValidationResponse> {
    return this.request<TokenValidationResponse>('/validate', {
      headers: {
        'x-auth-source': 'AUTH_TOKEN',
      },
    });
  }

  async getCurrentUser(): Promise<User> {
    // Use a longer timeout for /me endpoint as it's critical for auth validation
    return this.requestWithTimeout<User>('/me', {
      headers: {
        'x-auth-source': 'AUTH_TOKEN',
      },
    }, 20000); // 20 seconds timeout for /me endpoint
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

    // Use custom timeout
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    
    try {
      const response = await fetch(url, {
        ...config,
        signal: controller.signal,
      });
      
      clearTimeout(timeoutId);
      
      if (!response.ok) {
        let errorData: any = {};
        try {
          const text = await response.text();
          if (text) {
            errorData = JSON.parse(text);
          }
        } catch (e) {
          // If JSON parsing fails, use empty object
          errorData = {};
        }
        
        // Extract error message from various possible formats
        let errorMessage = `HTTP error! status: ${response.status}`;
        if (errorData?.detail) {
          errorMessage = String(errorData.detail);
        } else if (errorData?.message) {
          errorMessage = String(errorData.message);
        } else if (typeof errorData === 'string') {
          errorMessage = errorData;
        } else if (Array.isArray(errorData) && errorData.length > 0) {
          errorMessage = errorData.map((err: any) => err.detail || err.message || String(err)).join(', ');
        }
        
        // Add status code to error for better debugging
        const error = new Error(errorMessage);
        (error as any).status = response.status;
        throw error;
      }

      return await response.json();
    } catch (error: any) {
      clearTimeout(timeoutId);
      if (error.name === 'AbortError') {
        console.error('Auth service request timed out:', url);
        throw new Error(`Request timeout: Auth service is not responding (timeout: ${timeoutMs}ms)`);
      }
      console.error('Auth service request failed:', error);
      // Preserve the original error message and status if available
      if (error.status) {
        (error as any).status = error.status;
      }
      throw error;
    }
  }

  async updateCurrentUser(data: Partial<User>): Promise<User> {
    return this.request<User>('/me', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async changePassword(data: PasswordChangeRequest): Promise<{ message: string }> {
    return this.request<{ message: string }>('/change-password', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async requestPasswordReset(data: PasswordResetRequest): Promise<{ message: string }> {
    return this.request<{ message: string }>('/request-password-reset', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async resetPassword(data: PasswordResetConfirm): Promise<{ message: string }> {
    return this.request<{ message: string }>('/reset-password', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // API Key management
  async createApiKey(data: APIKeyCreate): Promise<APIKeyResponse> {
    return this.request<APIKeyResponse>('/api-keys', {
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
    return this.request<APIKeyResponse>('/api-keys', {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: {
        'x-auth-source': 'AUTH_TOKEN',
      },
    });
  }

  async listApiKeys(): Promise<APIKeyResponse[]> {
    return this.request<APIKeyResponse[]>('/api-keys');
  }

  async revokeApiKey(keyId: number): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/api-keys/${keyId}`, {
      method: 'DELETE',
    });
  }

  // OAuth2
  async getOAuth2Providers(): Promise<OAuth2Provider[]> {
    return this.request<OAuth2Provider[]>('/oauth2/providers');
  }

  // User management (Admin only)
  async getAllUsers(): Promise<User[]> {
    return this.request<User[]>('/users', {
      headers: {
        'x-auth-source': 'AUTH_TOKEN',
      },
    });
  }

  async getUserById(userId: number): Promise<User> {
    return this.request<User>(`/users/${userId}`, {
      headers: {
        'x-auth-source': 'AUTH_TOKEN',
      },
    });
  }

  // Permissions management (Admin only)
  async getAllPermissions(): Promise<string[]> {
    return this.request<string[]>('/permission/list', {
      headers: {
        'x-auth-source': 'AUTH_TOKEN',
      },
    });
  }

  // Utility methods
  isAuthenticated(): boolean {
    return !!this.getAccessToken();
  }

  getStoredUser(): User | null {
    if (typeof window === 'undefined') return null;
    // Check both storages (for backward compatibility)
    const userStr = localStorage.getItem('user') || sessionStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
  }

  setStoredUser(user: User): void {
    if (typeof window === 'undefined') return;
    const rememberMe = localStorage.getItem('remember_me') === 'true';
    // Clear from both storages first
    localStorage.removeItem('user');
    sessionStorage.removeItem('user');
    // Store in appropriate storage
    if (rememberMe) {
      localStorage.setItem('user', JSON.stringify(user));
    } else {
      sessionStorage.setItem('user', JSON.stringify(user));
    }
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

    // Check if token is expiring soon
    if (!this.isTokenExpiringSoon(thresholdMinutes)) {
      // Token is still valid for a while
      return true;
    }

    // Token is expiring soon or expired, try to refresh
    console.log('Token is expiring soon, attempting proactive refresh...');
    
    try {
      await this.refreshToken();
      console.log('Token refreshed successfully');
      return true;
    } catch (error) {
      console.error('Failed to refresh token:', error);
      // Don't clear tokens here - let the 401 handler deal with it
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

  // Session expiry tracking (24 hours)
  /**
   * Store the login timestamp
   */
  private setLoginTimestamp(): void {
    if (typeof window === 'undefined') return;
    const timestamp = Date.now().toString();
    const rememberMe = localStorage.getItem('remember_me') === 'true';
    // Clear from both storages first
    localStorage.removeItem('login_timestamp');
    sessionStorage.removeItem('login_timestamp');
    // Store in appropriate storage
    if (rememberMe) {
      localStorage.setItem('login_timestamp', timestamp);
    } else {
      sessionStorage.setItem('login_timestamp', timestamp);
    }
  }

  /**
   * Get the login timestamp
   */
  public getLoginTimestamp(): number | null {
    if (typeof window === 'undefined') return null;
    const timestampStr = localStorage.getItem('login_timestamp') || sessionStorage.getItem('login_timestamp');
    return timestampStr ? parseInt(timestampStr, 10) : null;
  }

  /**
   * Check if the session has expired (24 hours)
   */
  public isSessionExpired(): boolean {
    const loginTimestamp = this.getLoginTimestamp();
    if (!loginTimestamp) {
      // No timestamp found, consider expired
      return true;
    }
    const now = Date.now();
    const twentyFourHoursInMs = 24 * 60 * 60 * 1000; // 24 hours
    return (now - loginTimestamp) >= twentyFourHoursInMs;
  }

  /**
   * Get time remaining until session expiry in milliseconds
   */
  public getTimeUntilSessionExpiry(): number | null {
    const loginTimestamp = this.getLoginTimestamp();
    if (!loginTimestamp) {
      return null;
    }
    const now = Date.now();
    const twentyFourHoursInMs = 24 * 60 * 60 * 1000;
    const timeRemaining = twentyFourHoursInMs - (now - loginTimestamp);
    return timeRemaining > 0 ? timeRemaining : 0;
  }
}

export const authService = new AuthService();
export default authService;
