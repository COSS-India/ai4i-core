/**
 * Role management service for RBAC
 */
import type { ZodTypeAny } from 'zod';
import { z } from 'zod';
import { API_BASE_URL, apiService } from './api';
import { authUnwrappedSchema } from './dto/authUnwrappedSchema';
import { roleActionMessageSchema, roleSchema, userRoleSchema } from './dto/schemas/roles';
import { apiEndpoints } from './apiEndpoints';
import authService from './authService';

const rolePath = apiEndpoints.auth.rolePaths;

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

  private async request<S extends ZodTypeAny>(
    endpoint: string,
    schema: S,
    options: RequestInit = {}
  ): Promise<z.infer<S>> {
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
      const response = await apiService.request(
        (config.method || 'GET') as any,
        url,
        config.body,
        {
          headers: config.headers as Record<string, string>,
          responseSchema: authUnwrappedSchema(schema),
        }
      );
      return response.data as z.infer<S>;
    } catch (error: any) {
      const status = error?.response?.status;
      const errorData = error?.response?.data ?? {};
      const detail = errorData?.detail;
      const message =
        typeof detail === 'object' && detail !== null && typeof detail.message === 'string'
          ? detail.message
          : typeof detail === 'string'
            ? detail
            : status
              ? `HTTP error! status: ${status}`
              : 'Request failed';
      console.error('Role service request failed:', error);
      throw new Error(message);
    }
  }

  /**
   * List all available roles
   */
  async listRoles(): Promise<Role[]> {
    return this.request(rolePath.list, z.array(roleSchema), { method: 'GET' });
  }

  /**
   * Get roles for a specific user
   */
  async getUserRoles(userId: string): Promise<UserRole> {
    return this.request(rolePath.user(userId), userRoleSchema, { method: 'GET' });
  }

  /**
   * Assign a role to a user
   */
  async assignRole(userId: string, roleName: string): Promise<{ message: string }> {
    return this.request(rolePath.assign, roleActionMessageSchema, {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, role_name: roleName }),
    });
  }

  /**
   * Remove a role from a user
   */
  async removeRole(userId: string, roleName: string): Promise<{ message: string }> {
    return this.request(rolePath.remove, roleActionMessageSchema, {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, role_name: roleName }),
    });
  }
}

const roleService = new RoleService();
export default roleService;

