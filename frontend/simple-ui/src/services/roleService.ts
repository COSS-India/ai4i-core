/**
 * Role management service for RBAC
 */
import axios from 'axios';
import { apiEndpoints, apiRequest } from './api';
import authService from './authService';
import baseApiService from './baseApiService';

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

const rolePaths = apiEndpoints.auth.rolesPaths;

class RoleService {
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${apiEndpoints.auth.roles}${endpoint}`;
    
    const token = authService.getAccessToken();
    if (!token) {
      throw new Error('Not authenticated');
    }

    const method = (options.method || 'GET') as
      | 'GET'
      | 'POST'
      | 'PUT'
      | 'PATCH'
      | 'DELETE';
    const requestData =
      typeof options.body === 'string' ? JSON.parse(options.body) : options.body;

    return baseApiService.request<T>(url, {
      method,
      data: requestData,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        ...(options.headers as Record<string, string>),
      },
    };

    try {
      const method = (options.method || 'GET') as 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
      const requestData =
        typeof options.body === 'string' ? JSON.parse(options.body) : options.body;
      return await apiRequest<T>({
        url,
        method,
        data: requestData,
        headers: config.headers as Record<string, string>,
      });
    } catch (error) {
      if (axios.isAxiosError(error)) {
        const status = error.response?.status;
        const errorData: any = error.response?.data ?? {};
        const detail = errorData.detail;
        const message =
          typeof detail === 'object' && detail !== null && typeof detail.message === 'string'
            ? detail.message
            : typeof detail === 'string'
              ? detail
              : errorData?.message || error.message || `HTTP error! status: ${status ?? 'unknown'}`;
        const mappedError = new Error(message);
        (mappedError as any).status = status;
        throw mappedError;
      }
      console.error('Role service request failed:', error);
      throw error;
    }
  }

  /**
   * List all available roles
   */
  async listRoles(): Promise<Role[]> {
    return this.request<Role[]>(rolePaths.list);
  }

  /**
   * Get roles for a specific user
   */
  async getUserRoles(userId: string): Promise<UserRole> {
    return this.request<UserRole>(`${rolePaths.user}/${userId}`);
  }

  /**
   * Assign a role to a user
   */
  async assignRole(userId: string, roleName: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(rolePaths.assign, {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, role_name: roleName }),
    });
  }

  /**
   * Remove a role from a user
   */
  async removeRole(userId: string, roleName: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(rolePaths.remove, {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, role_name: roleName }),
    });
  }
}

const roleService = new RoleService();
export default roleService;

