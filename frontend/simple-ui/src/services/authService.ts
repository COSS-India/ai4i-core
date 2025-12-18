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

    try {
      const response = await fetch(url, config);
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Auth service request failed:', error);
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
        let errorMessage = `HTTP error! status: ${response.status}`;
        try {
          const errorData = await response.json();
          // Handle different error response formats
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
          } else if (typeof errorData === 'object') {
            // Try to extract meaningful error from object
            const errorText = errorData.detail || errorData.message || errorData.error;
            errorMessage = errorText ? String(errorText) : JSON.stringify(errorData);
          }
        } catch (jsonError) {
          // If response is not JSON, try to get text
          try {
            const text = await response.text();
            if (text) {
              errorMessage = text;
            }
          } catch (textError) {
            // Use default error message
            console.error('Failed to parse error response:', textError);
          }
        }
        throw new Error(errorMessage);
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
    return this.request<User>('/me', {
      headers: {
        'x-auth-source': 'AUTH_TOKEN',
      },
    });
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
    return this.request<APIKeyResponse>('/api-keys', {
      method: 'POST',
      body: JSON.stringify(data),
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

  // Auto-refresh token
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
}

export const authService = new AuthService();
export default authService;
