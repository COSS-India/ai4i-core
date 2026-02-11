// Tenant Management service API client for Adopter Admin

import { apiClient } from './api';

export interface Tenant {
  id: string;
  tenant_id: string;
  user_id: number;
  organization_name: string;
  email: string;
  domain: string;
  schema: string;
  subscriptions: string[];
  status: string;
  quotas: Record<string, any>;
  usage_quota: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface ListTenantsResponse {
  count: number;
  tenants: Tenant[];
}

export interface TenantUpdateRequest {
  tenant_id: string;
  organization_name?: string;
  contact_email?: string;
  domain?: string;
  requested_quotas?: Record<string, any>;
  usage_quota?: Record<string, any>;
}

export interface TenantUpdateResponse {
  tenant_id: string;
  message: string;
  changes: Record<string, { old: any; new: any }>;
  updated_fields: string[];
}

export interface TenantRegisterRequest {
  organization_name: string;
  domain: string;
  contact_email: string;
  requested_subscriptions?: string[];
  requested_quotas?: Record<string, any>;
  usage_quota?: Record<string, any>;
}

export interface TenantRegisterResponse {
  id: string;
  tenant_id: string;
  subdomain?: string;
  schema_name: string;
  validation_time?: string;
  status: string;
  token?: string;
  message?: string;
}

/**
 * List all tenants (admin endpoint - requires admin role)
 * Uses Bearer token authentication
 * @returns Promise with list of tenants
 */
export const listAdopterTenants = async (): Promise<Tenant[]> => {
  try {
    // Try adopter endpoint first (for adopter admins)
    try {
      const response = await apiClient.get<ListTenantsResponse>('/api/v1/multi-tenant/adopter/tenants');
      return response.data.tenants;
    } catch (adopterError: any) {
      // If adopter endpoint fails, try admin endpoint (for admins)
      const response = await apiClient.get<ListTenantsResponse>('/api/v1/multi-tenant/list/tenants');
      return response.data.tenants;
    }
  } catch (error: any) {
    console.error('List tenants error:', error);
    throw error;
  }
};

/**
 * Register a new tenant
 * @param registerData - The tenant registration data
 * @returns Promise with tenant registration response
 */
export const registerTenant = async (registerData: TenantRegisterRequest): Promise<TenantRegisterResponse> => {
  try {
    const response = await apiClient.post<TenantRegisterResponse>(
      '/api/v1/multi-tenant/register/tenant',
      registerData
    );
    return response.data;
  } catch (error: any) {
    console.error('Register tenant error:', error);
    throw error;
  }
};

/**
 * Update tenant information
 * @param updateData - The tenant update data
 * @returns Promise with updated tenant response
 */
export const updateTenant = async (updateData: TenantUpdateRequest): Promise<TenantUpdateResponse> => {
  try {
    const response = await apiClient.patch<TenantUpdateResponse>(
      '/api/v1/multi-tenant/update/tenant',
      updateData
    );
    return response.data;
  } catch (error: any) {
    console.error('Update tenant error:', error);
    throw error;
  }
};

/**
 * Resend verification email for a tenant
 * @param tenantId - The tenant ID
 * @returns Promise with resend verification response
 */
export const resendVerificationEmail = async (tenantId: string): Promise<{ tenant_id: string; token: string; message: string }> => {
  try {
    const response = await apiClient.post<{ tenant_id: string; token: string; message: string }>(
      '/api/v1/multi-tenant/email/resend',
      { tenant_id: tenantId }
    );
    return response.data;
  } catch (error: any) {
    console.error('Resend verification email error:', error);
    throw error;
  }
};

/**
 * Verify tenant email using token
 * @param token - The verification token
 * @returns Promise with verification response
 */
export const verifyTenantEmail = async (token: string): Promise<{ message: string }> => {
  try {
    const response = await apiClient.get<{ message: string }>(
      `/api/v1/multi-tenant/email/verify?token=${token}`
    );
    return response.data;
  } catch (error: any) {
    console.error('Verify tenant email error:', error);
    throw error;
  }
};

export interface TenantViewResponse {
  id: string;
  tenant_id: string;
  user_id: number;
  organization_name: string;
  email: string;
  domain: string;
  schema: string;
  subscriptions: string[];
  status: string;
  quotas: Record<string, any>;
  usage_quota: Record<string, any>;
  created_at: string;
  updated_at: string;
}

/**
 * Get tenant details by tenant_id
 * @param tenantId - The tenant ID
 * @returns Promise with tenant details
 */
export const getTenantDetails = async (tenantId: string): Promise<TenantViewResponse> => {
  try {
    const response = await apiClient.get<TenantViewResponse>(
      `/api/v1/multi-tenant/view/tenant?tenant_id=${tenantId}`
    );
    return response.data;
  } catch (error: any) {
    console.error('Get tenant details error:', error);
    throw error;
  }
};

export interface UsageIncrementRequest {
  tenant_id: string;
  characters_length: number;
  audio_length_in_min: number;
}

export interface UsageIncrementResponse {
  tenant_id: string;
  message: string;
  updated_usage: Record<string, any>;
}

/**
 * Check if tenant has enough quota for the requested usage
 * @param tenantId - The tenant ID
 * @param charactersLength - Characters to check (for NMT/TTS)
 * @param audioLengthMin - Audio minutes to check (for ASR)
 * @returns Object with hasQuota boolean and error message if quota exceeded
 */
export const checkTenantQuota = async (
  tenantId: string,
  charactersLength: number = 0,
  audioLengthMin: number = 0
): Promise<{ hasQuota: boolean; error?: string }> => {
  try {
    const tenant = await getTenantDetails(tenantId);
    const quotas = tenant.quotas || {};
    const currentUsage = tenant.usage_quota || {};
    
    const quotaChars = quotas.characters_length;
    const quotaAudio = quotas.audio_length_in_min;
    const usageChars = currentUsage.characters_length || 0;
    const usageAudio = currentUsage.audio_length_in_min || 0;
    
    // Calculate new usage after this request
    const newUsageChars = usageChars + charactersLength;
    const newUsageAudio = usageAudio + audioLengthMin;
    
    const errors: string[] = [];
    
    // Check characters quota (for NMT/TTS)
    if (charactersLength > 0 && quotaChars !== undefined && quotaChars !== null) {
      if (newUsageChars > quotaChars) {
        const remaining = Math.max(0, quotaChars - usageChars);
        errors.push(
          `Characters quota exceeded. You have ${remaining.toLocaleString()} characters remaining, but need ${charactersLength.toLocaleString()}.`
        );
      }
    }
    
    // Check audio quota (for ASR)
    if (audioLengthMin > 0 && quotaAudio !== undefined && quotaAudio !== null) {
      if (newUsageAudio > quotaAudio) {
        const remaining = Math.max(0, quotaAudio - usageAudio);
        errors.push(
          `Audio quota exceeded. You have ${remaining.toFixed(2)} minutes remaining, but need ${audioLengthMin.toFixed(2)} minutes.`
        );
      }
    }
    
    if (errors.length > 0) {
      return {
        hasQuota: false,
        error: errors.join(' ')
      };
    }
    
    return { hasQuota: true };
  } catch (error: any) {
    // If we can't check quota, allow the request (fail open)
    console.warn('Failed to check quota, allowing request:', error);
    return { hasQuota: true };
  }
};

/**
 * Increment tenant usage quota using the update API
 * Fetches current usage, calculates new values, and updates via update tenant API
 * @param incrementData - The usage increment data
 * @returns Promise with usage increment response
 */
export const incrementTenantUsage = async (
  incrementData: UsageIncrementRequest
): Promise<UsageIncrementResponse> => {
  try {
    // First, fetch current tenant details to get current usage
    const tenant = await getTenantDetails(incrementData.tenant_id);
    
    // Calculate new usage values
    const currentUsage = tenant.usage_quota || {};
    const newUsage = {
      characters_length: (currentUsage.characters_length || 0) + incrementData.characters_length,
      audio_length_in_min: Math.round(((currentUsage.audio_length_in_min || 0) + incrementData.audio_length_in_min) * 100) / 100, // Round to 2 decimal places
    };
    
    // Update tenant with new usage values
    const updateResponse = await updateTenant({
      tenant_id: incrementData.tenant_id,
      usage_quota: newUsage,
    });
    
    // Return response in the format expected by callers
    return {
      tenant_id: incrementData.tenant_id,
      message: updateResponse.message || 'Usage incremented successfully',
      updated_usage: newUsage,
    };
  } catch (error: any) {
    console.error('Increment usage error:', error);
    throw error;
  }
};
