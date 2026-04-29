/**
 * Role management service for RBAC
 */
import { API_BASE_URL } from './api';
import { apiEndpoints } from './apiEndpoints';
import authService from './authService';

export interface Role {
  id: number;
  name: string;
  description: string;
}

export interface UserRole {
  user_id: string;
  username: string;
  email: string;
  roles: string[];
}

class RoleService {
  private baseUrl: string;

  constructor() {
    this.baseUrl = `${API_BASE_URL}${apiEndpoints.auth.rolesBase}`;
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
        const detail = errorData.detail;
        const message =
          typeof detail === 'object' && detail !== null && typeof detail.message === 'string'
            ? detail.message
            : typeof detail === 'string'
              ? detail
              : `HTTP error! status: ${response.status}`;
        throw new Error(message);
      }

      const json = await response.json();
      // Unwrap v2 response envelope: { success: true, data: {...} }
      if (json && typeof json === 'object' && 'success' in json && 'data' in json) {
        return json.data as T;
      }
      return json as T;
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
  async getUserRoles(userId: string): Promise<UserRole> {
    return this.request<UserRole>(`/user/${userId}`);
  }

  /**
   * Assign a role to a user
   */
  async assignRole(userId: string, roleName: string): Promise<{ message: string }> {
    return this.request<{ message: string }>('/assign', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, role_name: roleName }),
    });
  }

  /**
   * Remove a role from a user
   */
  async removeRole(userId: string, roleName: string): Promise<{ message: string }> {
    return this.request<{ message: string }>('/remove', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, role_name: roleName }),
    });
  }
}

const roleService = new RoleService();
export default roleService;

