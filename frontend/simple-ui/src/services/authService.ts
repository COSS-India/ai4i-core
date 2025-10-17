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
} from '../types/auth';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

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

  // Token management
  private getAccessToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('access_token');
  }

  private setAccessToken(token: string): void {
    if (typeof window === 'undefined') return;
    localStorage.setItem('access_token', token);
  }

  private getRefreshToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('refresh_token');
  }

  private setRefreshToken(token: string): void {
    if (typeof window === 'undefined') return;
    localStorage.setItem('refresh_token', token);
  }

  private clearTokens(): void {
    if (typeof window === 'undefined') return;
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  }

  // Authentication methods
  async register(data: RegisterRequest): Promise<User> {
    return this.request<User>('/register', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async login(data: LoginRequest): Promise<LoginResponse> {
    const response = await this.request<LoginResponse>('/login', {
      method: 'POST',
      body: JSON.stringify(data),
    });

    // Store tokens
    this.setAccessToken(response.access_token);
    this.setRefreshToken(response.refresh_token);

    return response;
  }

  async logout(data: LogoutRequest = {}): Promise<LogoutResponse> {
    const refreshToken = this.getRefreshToken();
    const response = await this.request<LogoutResponse>('/logout', {
      method: 'POST',
      body: JSON.stringify({
        ...data,
        refresh_token: data.refresh_token || refreshToken,
      }),
    });

    // Clear tokens
    this.clearTokens();

    return response;
  }

  async refreshToken(): Promise<TokenRefreshResponse> {
    const refreshToken = this.getRefreshToken();
    if (!refreshToken) {
      throw new Error('No refresh token available');
    }

    const response = await this.request<TokenRefreshResponse>('/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    // Update access token
    this.setAccessToken(response.access_token);

    return response;
  }

  async validateToken(): Promise<TokenValidationResponse> {
    return this.request<TokenValidationResponse>('/validate');
  }

  async getCurrentUser(): Promise<User> {
    return this.request<User>('/me');
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

  // Utility methods
  isAuthenticated(): boolean {
    return !!this.getAccessToken();
  }

  getStoredUser(): User | null {
    if (typeof window === 'undefined') return null;
    const userStr = localStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
  }

  setStoredUser(user: User): void {
    if (typeof window === 'undefined') return;
    localStorage.setItem('user', JSON.stringify(user));
  }

  clearStoredUser(): void {
    if (typeof window === 'undefined') return;
    localStorage.removeItem('user');
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
