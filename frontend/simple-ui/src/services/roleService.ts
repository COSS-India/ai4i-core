/**
 * Role management service for RBAC
 */
import { API_BASE_URL } from './api';
import authService from './authService';

export interface Role {
  id: number;
  name: string;
  description: string;
}

export interface UserRole {
  user_id: number;
  username: string;
  email: string;
  roles: string[];
}

class RoleService {
  private baseUrl: string;

  constructor() {
    this.baseUrl = `${API_BASE_URL}/api/v1/auth/roles`;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    
    const token = authService.getAccessToken();
    if (!token) {
      throw new Error('Not authenticated');
    }

    const config: RequestInit = {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
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
      console.error('Role service request failed:', error);
      throw error;
    }
  }

  /**
   * List all available roles
   */
  async listRoles(): Promise<Role[]> {
    return this.request<Role[]>('/list');
  }

  /**
   * Get roles for a specific user
   */
  async getUserRoles(userId: number): Promise<UserRole> {
    return this.request<UserRole>(`/user/${userId}`);
  }

  /**
   * Assign a role to a user
   */
  async assignRole(userId: number, roleName: string): Promise<{ message: string }> {
    return this.request<{ message: string }>('/assign', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, role_name: roleName }),
    });
  }

  /**
   * Remove a role from a user
   */
  async removeRole(userId: number, roleName: string): Promise<{ message: string }> {
    return this.request<{ message: string }>('/remove', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, role_name: roleName }),
    });
  }
}

export default new RoleService();

